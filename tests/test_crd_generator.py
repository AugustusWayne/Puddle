import pytest
from generator.parser       import load_input, ParseError
from generator.validator    import validate_fields
from generator.crd_generator import generate_crd
from generator.cr_generator  import generate_cr


SAMPLE_RESOURCE = {
    "group":   "myapp.io",
    "version": "v1alpha1",
    "kind":    "Database",
    "scope":   "Namespaced",
    "fields": [
        {"name": "engine",   "type": "string",  "required": True,  "enum": ["postgres", "mysql"]},
        {"name": "replicas", "type": "integer", "required": True,  "minimum": 1, "maximum": 10},
        {"name": "storage",  "type": "integer", "required": False, "default": 20},
    ],
}


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
        spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
        assert "engine" in spec["required"]
        assert "replicas" in spec["required"]
        assert "storage" not in spec.get("required", [])

    def test_enum_preserved(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        spec_props = (
            crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
               ["properties"]["spec"]["properties"]
        )
        assert spec_props["engine"]["enum"] == ["postgres", "mysql"]

    def test_subresource_status_present(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        assert "status" in crd["spec"]["versions"][0]["subresources"]

    def test_printer_columns_include_age(self):
        crd = generate_crd(SAMPLE_RESOURCE)
        cols = crd["spec"]["versions"][0]["additionalPrinterColumns"]
        names = [c["name"] for c in cols]
        assert "Age" in names


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
