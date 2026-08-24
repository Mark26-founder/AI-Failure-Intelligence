import aifi


def test_package_version():
    assert hasattr(aifi, "__version__")
    assert aifi.__version__ == "0.1.0"
