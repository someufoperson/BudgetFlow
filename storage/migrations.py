from alembic import command
from alembic.config import Config

from settings import BASE_DIR


def upgrade_database() -> None:
    config_path = BASE_DIR / "alembic.ini"
    config = Config(str(config_path))

    command.upgrade(config, "head")
