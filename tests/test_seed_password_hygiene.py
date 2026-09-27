"""Seed account creation must obtain private, fresh credentials."""
import ast
from pathlib import Path

import pytest

from new_architecture import add_users


def test_seed_data_contains_no_password_literals():
    tree = ast.parse(Path(add_users.__file__).read_text())
    seed = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'USERS_TO_ADD'
                        for target in node.targets))
    for account in seed.elts:
        assert all(not (isinstance(key, ast.Constant) and key.value == 'password')
                   for key in account.keys)
    db_secret = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'DB_PASSWORD'
                             for target in node.targets))
    assert isinstance(db_secret, ast.Call) and len(db_secret.args) == 1
    assert isinstance(db_secret.args[0], ast.Constant)
    assert db_secret.args[0].value == 'POSTGRES_PASSWORD'


def test_seed_password_private_prompt_or_supplied_secret(monkeypatch):
    monkeypatch.delenv('RAGBOT_SEED_PASSWORD_EXAMPLE', raising=False)
    prompts = []
    monkeypatch.setattr(add_users, 'getpass', lambda label: prompts.append(label) or 'x' * 12)
    assert add_users.password_for_seed('example') == 'x' * 12
    assert len(prompts) == 1
    monkeypatch.setenv('RAGBOT_SEED_PASSWORD_EXAMPLE', 'y' * 12)
    assert add_users.password_for_seed('example') == 'y' * 12
    assert len(prompts) == 1
    monkeypatch.setenv('RAGBOT_SEED_PASSWORD_EXAMPLE', 'short')
    with pytest.raises(ValueError):
        add_users.password_for_seed('example')
