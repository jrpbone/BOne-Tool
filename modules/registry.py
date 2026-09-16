"""Feature registry. Add new workspace controllers to FEATURE_TYPES."""

from .crypto import CryptoFeature
from .hashing import HashFeature
from .image_ascii import AsciiFeature
from .encoding import EncodingFeature

FEATURE_TYPES = (CryptoFeature, HashFeature, AsciiFeature, EncodingFeature)
