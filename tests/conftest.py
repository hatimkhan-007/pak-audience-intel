import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from campaign_engine import config, pipeline


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    config.DB_PATH = d / "t.db"; config.MODEL_PATH = d / "m.joblib"; config.TRUTH_PATH = d / "truth.csv"
    pipeline.build(n_posts=500, seed=7, verbose=False)
    return config.DB_PATH


@pytest.fixture()
def client(built):
    from campaign_engine.webapp import create_app
    return create_app().test_client()
