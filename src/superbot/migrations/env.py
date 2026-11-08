from alembic import context

from superbot.core.db import make_engine

# No fileConfig: the app owns logging setup.
engine = make_engine(context.config.get_main_option("sqlalchemy.url"))
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
