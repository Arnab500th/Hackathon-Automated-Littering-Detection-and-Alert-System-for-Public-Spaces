from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATATBASE_URL="sqlite:///./main.db"
connect_args = {"check_same_thread": False}
engine=create_engine(DATATBASE_URL,connect_args=connect_args)

session= sessionmaker(autocommit=False, autoflush=False, bind=engine)