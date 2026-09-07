import numpy as np
import pytest

from ioaudit import AccountingConvention, IOSystem


@pytest.fixture
def normal_data():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    sectors = ["A", "B"]
    y = np.array([[5.0], [5.0]])
    v = np.array([[5.0, 5.0]])
    convention = AccountingConvention.domestic_competitive()
    return z, x, sectors, y, v, convention


@pytest.fixture
def normal_io(normal_data):
    z, x, sectors, y, v, convention = normal_data
    return IOSystem(Z=z, x=x, sectors=sectors, Y=y, V=v, imports=np.zeros_like(x), accounting=convention)
