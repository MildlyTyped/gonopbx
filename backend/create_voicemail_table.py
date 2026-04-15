from database import engine, Base
from modules.voicemail.router import VoicemailRecord
Base.metadata.create_all(bind=engine)
print("✅ Voicemail table created!")
