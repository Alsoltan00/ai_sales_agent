# tests/test_auth.py
# اختبارات وحدة نظام المصادقة

import pytest

def test_login_as_admin_user():
    """اختبار تسجيل الدخول بحساب موظف -> يوجه لواجهة Admin"""
    pass

def test_login_as_merchant():
    """اختبار تسجيل الدخول بحساب عميل نشط -> يوجه لواجهة التاجر"""
    pass

def test_login_unknown_user_redirects_to_register():
    """اختبار أن المستخدم غير الموجود يُحوَّل لواجهة التسجيل"""
    pass

def test_register_new_client_creates_pending_request():
    """اختبار أن التسجيل يُنشئ طلباً بحالة pending"""
    pass

def test_register_existing_account_redirects_to_login():
    """اختبار أن تسجيل حساب موجود يُحوّل لتسجيل الدخول"""
    pass
