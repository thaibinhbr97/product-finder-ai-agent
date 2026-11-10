import pytest

from backend.agent.prompts import PROMPTS, get_prompt_template


@pytest.mark.parametrize("version", sorted(PROMPTS))
def test_prompt_renders(version):
    rendered = get_prompt_template(version).format(active_filters='{"category": "clothing"}')
    assert '{"category": "clothing"}' in rendered
    assert "{active_filters}" not in rendered


def test_v3_examples_keep_literal_braces():
    rendered = get_prompt_template("v3").format(active_filters="{}")
    assert 'Active {"category": "clothing"} | "which ones are red?"' in rendered


def test_unknown_version():
    with pytest.raises(ValueError):
        get_prompt_template("v99")
