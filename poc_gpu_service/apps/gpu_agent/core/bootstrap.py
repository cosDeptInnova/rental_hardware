from apps.gpu_agent.db.session import engine
from apps.gpu_agent.models.db_models import Base


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
