from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Always creates main.db in the backend/ folder
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'main.db')}"

engine  = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
session = sessionmaker(autocommit=False, autoflush=False, bind=engine)