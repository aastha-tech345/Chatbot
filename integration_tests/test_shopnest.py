from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.modules.orders.presentation import routes as orders
from app.modules.returns.presentation import routes as returns


def test_status_list_only_uses_current_customers_orders(monkeypatch):
    delivered = SimpleNamespace(id='item-1', status='delivered')
    pending = SimpleNamespace(id='item-2', status='pending')
    reader = Mock(return_value=[SimpleNamespace(items=[delivered, pending])])
    monkeypatch.setattr(orders, 'list_orders_for_user', reader)
    db = object()
    assert orders.my_order_items(status='delivered', current_user=SimpleNamespace(id='alice'), db=db) == [delivered]
    reader.assert_called_once_with(db, user_id='alice')


def test_cancellation_uses_existing_customer_policy(monkeypatch):
    cancel = Mock(return_value={'status':'failed','message':'Already shipped'})
    monkeypatch.setattr(orders,'cancel_order', cancel)
    db = Mock()
    with pytest.raises(HTTPException) as caught:
        orders.cancel_my_order('order-1', current_user=SimpleNamespace(id='alice'), db=db)
    assert caught.value.status_code == 400
    assert caught.value.detail == 'Already shipped'
    cancel.assert_called_once_with(db, user_id='alice', order_id='order-1')


def test_cancellation_hides_other_customers_orders(monkeypatch):
    monkeypatch.setattr(orders,'cancel_order',Mock(side_effect=ValueError('Order not found.')))
    db=Mock()
    with pytest.raises(HTTPException) as caught:
        orders.cancel_my_order('other-order',current_user=SimpleNamespace(id='alice'),db=db)
    assert caught.value.status_code == 404
    db.rollback.assert_called_once()


def test_refund_query_filters_current_user():
    db=Mock()
    db.scalars.return_value.all.return_value=[]
    assert returns.my_refunds(current_user=SimpleNamespace(id='alice'),db=db)==[]
    statement=db.scalars.call_args.args[0]
    assert 'orders.user_id' in str(statement)
    assert 'alice' in statement.compile().params.values()


def test_login_accepts_email_or_existing_user_uuid():
    from app.modules.identity.application.schemas import UserLoginRequest
    assert str(UserLoginRequest(email='test@example.com', password='test-only-password').email)=='test@example.com'
    assert str(UserLoginRequest(email='12345678-1234-1234-1234-123456789abc', password='test-only-password').email)=='12345678-1234-1234-1234-123456789abc'


def test_user_id_login_still_verifies_password(monkeypatch):
    from app.modules.identity.application import service
    from app.modules.identity.application.schemas import UserLoginRequest
    db=Mock()
    db.scalar.return_value=SimpleNamespace(id='12345678-1234-1234-1234-123456789abc', hashed_password='hash', is_active=True)
    verify=Mock(return_value=False)
    monkeypatch.setattr(service,'verify_password',verify)
    with pytest.raises(ValueError,match='Invalid credentials'):
        service.authenticate_user(db,UserLoginRequest(email='12345678-1234-1234-1234-123456789abc',password='incorrect-password'))
    verify.assert_called_once_with('incorrect-password','hash')
    assert 'users.id' in str(db.scalar.call_args.args[0])
