from farmbot.config import Config
from farmbot.form import apply_form, form_values


def test_builder_base_attacks_default_to_on_for_existing_configs():
    config = Config()
    assert config.builder.attack_enabled is True
    assert form_values(config)["builder.attack_enabled"] is True


def test_builder_base_attacks_can_be_disabled_in_settings():
    config = Config()
    apply_form(config, {"builder.attack_enabled": False})
    assert config.builder.attack_enabled is False
