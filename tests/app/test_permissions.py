import pytest
from app.permissions import check_permission
from app.models.enums import PermissionType
from app.models import AccountSource
from unittest.mock import Mock

user = Mock()
user.name = "test"
user.external_account_id = "test"
user.account_type = AccountSource.Twitch.value
user.broadcaster_id = 1234
user.is_anonymous = False
user.globally_banned = False

def test_check_permission():
    assert check_permission(user=user, check_anyone=True) == True

def test_deny_anonymous_users():
    user.is_anonymous = True
    assert check_permission(user=user, check_anyone=True) == False

def test_deny_banned_users():
    user.globally_banned = True
    assert check_permission(user=user, check_anyone=True) == False
    

    
