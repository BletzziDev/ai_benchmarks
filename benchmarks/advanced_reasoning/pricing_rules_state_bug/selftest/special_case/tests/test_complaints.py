from checkout import Cart, Customer, Line, price_cart


def test_cart_1():
    assert price_cart(Cart([Line("JKT", 5200)]), Customer("gold")).total == 5066


def test_cart_2():
    cart = Cart([Line("SOCK-A", 900, 2, bundle="socks"), Line("SOCK-B", 500, 1, on_sale=True, bundle="socks")])
    assert price_cart(cart).total == 3089
