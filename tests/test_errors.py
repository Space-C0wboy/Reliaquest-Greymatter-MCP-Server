from greymatter_mcp.errors import GreyMatterAPIError, GreyMatterGraphQLError


def test_api_error_carries_status_and_body():
    err = GreyMatterAPIError(503, "Service Unavailable", body={"x": 1})
    assert err.status_code == 503
    assert err.body == {"x": 1}
    assert "503" in str(err)


def test_graphql_error_summarizes_messages():
    errors = [{"message": "bad enum"}, {"message": "no perms"}]
    err = GreyMatterGraphQLError(errors)
    assert err.errors == errors
    assert "bad enum" in str(err)
    assert "no perms" in str(err)
