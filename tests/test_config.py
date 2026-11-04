import pytest

from source.config import AppConfig, _parse_email_list, _str_to_bool


def test_str_to_bool():
    assert _str_to_bool("true") is True
    assert _str_to_bool("1") is True
    assert _str_to_bool("yes") is True
    assert _str_to_bool("sim") is True
    assert _str_to_bool("s") is True
    assert _str_to_bool("y") is True
    assert _str_to_bool("false") is False
    assert _str_to_bool("0") is False
    assert _str_to_bool("nao") is False
    assert _str_to_bool(None, default=True) is True
    assert _str_to_bool(None, default=False) is False


def test_parse_email_list():
    # Comma separation
    res = _parse_email_list("a@test.com, b@test.com")
    assert res == ["a@test.com", "b@test.com"]

    # Semicolon separation
    res = _parse_email_list("a@test.com; b@test.com")
    assert res == ["a@test.com", "b@test.com"]

    # JSON array string
    res = _parse_email_list('["user1@test.com", "user2@test.com"]')
    assert res == ["user1@test.com", "user2@test.com"]

    # Empty or None
    assert _parse_email_list("") == []
    assert _parse_email_list(None) == []


def test_validate_essential_configs_success(mock_config):
    # Should not raise any exception
    mock_config.validate_essential_configs()


def test_validate_essential_configs_missing_fields():
    config = AppConfig()
    with pytest.raises(ValueError) as excinfo:
        config.validate_essential_configs()

    err = str(excinfo.value)
    assert "LEGALONE_EMAIL não configurado" in err
    assert "NEXTCLOUD_URL não configurado" in err
    assert "SMTP_HOST não configurado" in err
    assert "ADMIN_EMAIL não configurado" in err
