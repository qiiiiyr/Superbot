def test_main_imports():
    import superbot.main

    assert callable(superbot.main.run)
