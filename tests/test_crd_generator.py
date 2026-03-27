"""
tests/test_crd_generator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the k8s-cr-generator core engine and web API.

Run with:
    pytest tests/ -v
"""

import json
import pytest

from generator.parser        import load_input, ParseError
from generator.validator     import validate_fields
from generator.crd_generator import generate_crd, _short_name, _pluralise
from generator.cr_generator  import generate_cr
from generator.writer        import to_yaml_string


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESOURCE = {
    "group":   "myapp.io",
    "version": "v1alpha1",
    "kind":    "Database",
    "scope":   "Namespaced",
    "fields": [
        {"name": "engine",   "type": "string",  "required": True,
         "enum": ["postgres", "mysql"]},
        {"name": "replicas", "type": "integer", "required": True,
         "minimum": 1, "maximum": 10},
        {"name": "storage",  "type": "integer", "required": False, "default": 20},
    ],
}


# ---------------------------------------------------------------------------
# TestPluralise
# ---------------------------------------------------------------------------

class TestPluralise:
    def test_regular_word(self):
        assert _pluralise("Database") == "databases"

    def test_s_ending(self):
        assert _pluralise("Redis") == "redises"

    def test_x_ending(self):
        assert _pluralise("Index") == "indexes"

    def test_y_ending_consonant(self):
        assert _pluralise("Policy") == "policies"

    def test_y_ending_vowel(self):
        # "Monkey" ends in vowel+y → just append s
        assert _pluralise("Monkey") == "monkeys"

    def test_ch_ending(self):
        assert _pluralise("Watch") == "watches"


# ---------------------------------------------------------------------------
# TestShortName
# ---------------------------------------------------------------------------

class TestShortName:
    def test_database(self):
        # D + first consonant after D in 'Database' = t → 'dt'
        assert _short_name("Database") == "dt"

    def test_database2(self):
        # Same logic + digit suffix
        assert _short_name("Database2") == "dt2"

    def test_redis(self):
        assert _short_name("Redis") == "rd"

    def test_single_char(self):
        # Degenerate: kind is only one letter
        name = _short_name("X")
        assert len(name) >= 1

    def test_no_digit_suffix(self):
        assert not any(c.isdigit() for c in _short_name("Database"))

    def test_digit_suffix_preserved(self):
        assert _short_name("Database3").endswith("3")


# ---------------------------------------------------------------------------
# TestCRDGenerator
# ---------------------------------------------------------------------------

class TestCRDGenerator:
    def test_crd_api_version(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        assert crd["apiVersion"] == "apiextensions.k8s.io/v1"

    def test_crd_name_format(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        assert crd["metadata"]["name"] == "databases.myapp.io"

    def test_crd_has_spec_schema(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        assert "spec" in schema["properties"]

    def test_required_fields_present(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        spec = (crd["spec"]["versions"][0]["schema"]
                   ["openAPIV3Schema"]["properties"]["spec"])
        assert "engine"   in spec["required"]
        assert "replicas" in spec["required"]
        assert "storage"  not in spec.get("required", [])

    def test_enum_preserved(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        props = (crd["spec"]["versions"][0]["schema"]
                    ["openAPIV3Schema"]["properties"]["spec"]["properties"])
        assert props["engine"]["enum"] == ["postgres", "mysql"]

    def test_subresource_status_present(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        assert "status" in crd["spec"]["versions"][0]["subresources"]

    def test_printer_columns_include_age(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        cols  = crd["spec"]["versions"][0]["additionalPrinterColumns"]
        names = [c["name"] for c in cols]
        assert "Age" in names

    def test_short_name_in_crd(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        assert "dt" in crd["spec"]["names"]["shortNames"]

    def test_numbered_kind_short_name_unique(self):
        """Database and Database2 must produce different short names."""
        r2 = {**SAMPLE_RESOURCE, "kind": "Database2"}
        crd1 = generate_crd(SAMPLE_RESOURCE)
        crd2 = generate_crd(r2)
        sn1 = crd1["spec"]["names"]["shortNames"][0]
        sn2 = crd2["spec"]["names"]["shortNames"][0]
        assert sn1 != sn2

    def test_index_plural(self):
        r = {**SAMPLE_RESOURCE, "kind": "Index"}
        crd = generate_crd(r)
        assert crd["spec"]["names"]["plural"] == "indexes"

    def test_policy_plural(self):
        r = {**SAMPLE_RESOURCE, "kind": "Policy"}
        crd = generate_crd(r)
        assert crd["spec"]["names"]["plural"] == "policies"


# ---------------------------------------------------------------------------
# TestCRGenerator
# ---------------------------------------------------------------------------

class TestCRGenerator:
    def test_cr_api_version(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert cr["apiVersion"] == "myapp.io/v1alpha1"

    def test_cr_uses_first_enum_value(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert cr["spec"]["engine"] == "postgres"

    def test_cr_default_value(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert cr["spec"]["storage"] == 20

    def test_cr_minimum_used_when_no_default(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert cr["spec"]["replicas"] == 1   # minimum

    def test_cr_custom_name(self):
        cr = generate_cr(SAMPLE_RESOURCE, name="prod-db")
        assert cr["metadata"]["name"] == "prod-db"

    def test_cr_default_name(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert cr["metadata"]["name"] == "sample-database"

    def test_cr_has_managed_by_label(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        labels = cr["metadata"].get("labels", {})
        assert "app.kubernetes.io/managed-by" in labels


# ---------------------------------------------------------------------------
# TestValidator
# ---------------------------------------------------------------------------

class TestValidator:
    def test_minimum_greater_than_maximum_fails(self):
        fields = [{"name": "x", "type": "integer", "minimum": 10, "maximum": 5}]
        with pytest.raises(ParseError):
            validate_fields(fields)

    def test_pattern_on_non_string_fails(self):
        fields = [{"name": "x", "type": "integer", "pattern": "^[0-9]+$"}]
        with pytest.raises(ParseError):
            validate_fields(fields)

    def test_wrong_enum_type_fails(self):
        fields = [{"name": "x", "type": "integer", "enum": ["a", "b"]}]
        with pytest.raises(ParseError):
            validate_fields(fields)

    def test_minimum_on_string_fails(self):
        fields = [{"name": "x", "type": "string", "minimum": 1}]
        with pytest.raises(ParseError):
            validate_fields(fields)

    def test_bad_default_type_fails(self):
        fields = [{"name": "x", "type": "integer", "default": "not-an-int"}]
        with pytest.raises(ParseError):
            validate_fields(fields)

    def test_valid_field_passes(self):
        fields = [{"name": "x", "type": "string", "default": "hello", "pattern": "^[a-z]+$"}]
        validate_fields(fields)   # should not raise


# ---------------------------------------------------------------------------
# TestWriter
# ---------------------------------------------------------------------------

class TestWriter:
    def test_to_yaml_string_contains_api_version(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        yaml_str = to_yaml_string(crd)
        assert "apiextensions.k8s.io/v1" in yaml_str

    def test_to_yaml_string_is_string(self):
        cr = generate_cr(SAMPLE_RESOURCE)
        assert isinstance(to_yaml_string(cr), str)


# ---------------------------------------------------------------------------
# TestWebApp
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from web.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestWebApp:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_generate_valid_payload(self, client):
        payload = {"resource": SAMPLE_RESOURCE}
        resp = client.post(
            "/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "crd_yaml" in body
        assert "cr_yaml"  in body
        assert body["errors"] == []

    def test_generate_missing_resource_key(self, client):
        resp = client.post(
            "/generate",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["errors"]

    def test_generate_invalid_field_returns_422(self, client):
        bad = {**SAMPLE_RESOURCE, "fields": [
            {"name": "x", "type": "integer", "minimum": 10, "maximum": 1},
        ]}
        resp = client.post(
            "/generate",
            data=json.dumps({"resource": bad}),
            content_type="application/json",
        )
        assert resp.status_code == 422
