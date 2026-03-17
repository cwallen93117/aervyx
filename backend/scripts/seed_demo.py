from app.db import Base, SessionLocal, engine
from app.services.seeding import bootstrap_demo_data


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        bootstrap_demo_data(session)
        session.commit()
        print("Demo data seeded.")
    finally:
        session.close()