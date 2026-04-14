"""
Asterisk PBX GUI - Backend API
FastAPI application with Asterisk AMI integration
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
import uvicorn
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our modules
import os
from ami_client import AsteriskAMIClient
from database import engine, Base
from auth import get_password_hash
from database import SessionLocal, User, SIPPeer, VoicemailMailbox, SystemSettings
from voicemail_config import write_voicemail_config, reload_voicemail
from email_config import write_msmtp_config
from mqtt_client import mqtt_publisher
from version import VERSION

# Directory that contains the pre-built frontend SPA (populated by the
# multi-stage Docker build).  Absent in pure backend dev mode.
FRONTEND_DIST_DIR = Path(__file__).parent / "frontend_dist"

# Module system — importing this package registers all built-in modules with
# the global module_registry as a side-effect.
import modules  # noqa: F401
from pbxgen.module import module_registry
from pbxgen.ami import AMIProxy

# Global AMI client instance
ami_client = None


# Lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global ami_client
    
    # Startup
    logger.info("Starting Asterisk PBX GUI Backend...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Migrate: add codecs column to sip_peers if missing
    try:
        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('sip_peers')]
        if 'codecs' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE sip_peers ADD COLUMN codecs VARCHAR(200)"))
                conn.commit()
            logger.info("Migration: added codecs column to sip_peers")
    except Exception as e:
        logger.warning(f"Migration check for codecs column: {e}")

    # Migrate: add ring_timeout column to voicemail_mailboxes if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect
        vm_inspector = sa_inspect(engine)
        vm_columns = [c['name'] for c in vm_inspector.get_columns('voicemail_mailboxes')]
        if 'ring_timeout' not in vm_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE voicemail_mailboxes ADD COLUMN ring_timeout INTEGER DEFAULT 20"))
                conn.commit()
            logger.info("Migration: added ring_timeout column to voicemail_mailboxes")
    except Exception as e:
        logger.warning(f"Migration check for ring_timeout column: {e}")

    # Migrate: add outbound_cid and pai columns to sip_peers if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_peers
        peers_inspector = sa_inspect_peers(engine)
        peer_columns = [c['name'] for c in peers_inspector.get_columns('sip_peers')]
        with engine.connect() as conn:
            if 'outbound_cid' not in peer_columns:
                conn.execute(text("ALTER TABLE sip_peers ADD COLUMN outbound_cid VARCHAR(50)"))
                logger.info("Migration: added outbound_cid column to sip_peers")
            if 'pai' not in peer_columns:
                conn.execute(text("ALTER TABLE sip_peers ADD COLUMN pai VARCHAR(50)"))
                logger.info("Migration: added pai column to sip_peers")
            conn.commit()
    except Exception as e:
        logger.warning(f"Migration check for outbound_cid/pai columns: {e}")

    # Migrate: add avatar_url column to users if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_users
        users_inspector = sa_inspect_users(engine)
        users_columns = [c['name'] for c in users_inspector.get_columns('users')]
        if 'avatar_url' not in users_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255)"))
                conn.commit()
            logger.info("Migration: added avatar_url column to users")
    except Exception as e:
        logger.warning(f"Migration check for avatar_url column: {e}")

    # Migrate: drop unique constraint on users.email if it exists
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"))
            conn.commit()
        logger.info("Migration: dropped unique constraint on users.email")
    except Exception as e:
        logger.warning(f"Migration check for users.email unique constraint: {e}")

    # Migrate: add blf_enabled column to sip_peers if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_blf
        blf_inspector = sa_inspect_blf(engine)
        blf_columns = [c['name'] for c in blf_inspector.get_columns('sip_peers')]
        if 'blf_enabled' not in blf_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE sip_peers ADD COLUMN blf_enabled BOOLEAN DEFAULT TRUE"))
                conn.commit()
            logger.info("Migration: added blf_enabled column to sip_peers")
    except Exception as e:
        logger.warning(f"Migration check for blf_enabled column: {e}")

    # Migrate: add pickup_group column to sip_peers if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_pg
        pg_inspector = sa_inspect_pg(engine)
        pg_columns = [c['name'] for c in pg_inspector.get_columns('sip_peers')]
        if 'pickup_group' not in pg_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE sip_peers ADD COLUMN pickup_group VARCHAR(50)"))
                conn.commit()
            logger.info("Migration: added pickup_group column to sip_peers")
    except Exception as e:
        logger.warning(f"Migration check for pickup_group column: {e}")

    # Migrate: create ivr tables if missing
    try:
        from sqlalchemy import inspect as sa_inspect_ivr
        ivr_inspector = sa_inspect_ivr(engine)
        tables = ivr_inspector.get_table_names()
        if 'ivr_menus' not in tables:
            from database import IVRMenu
            IVRMenu.__table__.create(bind=engine)
            logger.info("Migration: created ivr_menus table")
        if 'ivr_options' not in tables:
            from database import IVROption
            IVROption.__table__.create(bind=engine)
            logger.info("Migration: created ivr_options table")
    except Exception as e:
        logger.warning(f"Migration check for ivr tables: {e}")

    # Migrate: add retries/inbound columns to ivr_menus if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_ivr_cols
        ivr_col_inspector = sa_inspect_ivr_cols(engine)
        if 'ivr_menus' in ivr_col_inspector.get_table_names():
            ivr_cols = [c['name'] for c in ivr_col_inspector.get_columns('ivr_menus')]
            with engine.connect() as conn:
                if 'retries' not in ivr_cols:
                    conn.execute(text("ALTER TABLE ivr_menus ADD COLUMN retries INTEGER DEFAULT 2"))
                    logger.info("Migration: added retries column to ivr_menus")
                if 'inbound_trunk_id' not in ivr_cols:
                    conn.execute(text("ALTER TABLE ivr_menus ADD COLUMN inbound_trunk_id INTEGER"))
                    logger.info("Migration: added inbound_trunk_id column to ivr_menus")
                if 'inbound_did' not in ivr_cols:
                    conn.execute(text("ALTER TABLE ivr_menus ADD COLUMN inbound_did VARCHAR(50)"))
                    logger.info("Migration: added inbound_did column to ivr_menus")
                conn.commit()
    except Exception as e:
        logger.warning(f"Migration check for ivr_menus columns: {e}")

    # Migrate: add inbound_trunk_id and inbound_did columns to ring_groups if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_rg
        rg_inspector = sa_inspect_rg(engine)
        if 'ring_groups' in rg_inspector.get_table_names():
            rg_columns = [c['name'] for c in rg_inspector.get_columns('ring_groups')]
            with engine.connect() as conn:
                if 'inbound_trunk_id' not in rg_columns:
                    conn.execute(text("ALTER TABLE ring_groups ADD COLUMN inbound_trunk_id INTEGER"))
                    logger.info("Migration: added inbound_trunk_id column to ring_groups")
                if 'inbound_did' not in rg_columns:
                    conn.execute(text("ALTER TABLE ring_groups ADD COLUMN inbound_did VARCHAR(50)"))
                    logger.info("Migration: added inbound_did column to ring_groups")
                conn.commit()
    except Exception as e:
        logger.warning(f"Migration check for ring_groups inbound columns: {e}")

    # Migrate: add from_user column to sip_trunks if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect_trunks
        trunks_inspector = sa_inspect_trunks(engine)
        if 'sip_trunks' in trunks_inspector.get_table_names():
            trunk_columns = [c['name'] for c in trunks_inspector.get_columns('sip_trunks')]
            if 'from_user' not in trunk_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE sip_trunks ADD COLUMN from_user VARCHAR(100)"))
                    conn.commit()
                logger.info("Migration: added from_user column to sip_trunks")
    except Exception as e:
        logger.warning(f"Migration check for from_user column: {e}")

    # Migrate: create audit_logs table if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect2
        al_inspector = sa_inspect2(engine)
        if 'audit_logs' not in al_inspector.get_table_names():
            from database import AuditLog
            AuditLog.__table__.create(bind=engine)
            logger.info("Migration: created audit_logs table")
    except Exception as e:
        logger.warning(f"Migration check for audit_logs table: {e}")

    # Seed admin user if not exists
    db = SessionLocal()
    try:
        admin_pw = os.getenv("ADMIN_PASSWORD", "GonoPBX2026!")
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@gonopbx.local",
                password_hash=get_password_hash(admin_pw),
                full_name="Administrator",
                role="admin",
            )
            db.add(admin)
            db.commit()
            logger.info("Admin user created")
        else:
            # Update password to match current ADMIN_PASSWORD env var
            admin.password_hash = get_password_hash(admin_pw)
            db.commit()
            logger.info("Admin user password synced with ADMIN_PASSWORD env")
        # Migrate: create voicemail mailboxes for existing peers
        peers = db.query(SIPPeer).all()
        created = 0
        for peer in peers:
            existing_mb = db.query(VoicemailMailbox).filter(VoicemailMailbox.extension == peer.extension).first()
            if not existing_mb:
                mb = VoicemailMailbox(extension=peer.extension, name=peer.caller_id or peer.extension)
                db.add(mb)
                created += 1
        if created > 0:
            db.commit()
            logger.info(f"Created {created} voicemail mailboxes for existing peers")

        # Load SMTP settings from DB
        smtp_settings = {}
        for key in ["smtp_host", "smtp_port", "smtp_tls", "smtp_user", "smtp_password", "smtp_from"]:
            s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            smtp_settings[key] = s.value if s else ""

        # Write msmtp config if SMTP is configured
        if smtp_settings.get("smtp_host"):
            write_msmtp_config(smtp_settings)
            logger.info("msmtp config written to Asterisk container")

        # Regenerate voicemail.conf with SMTP settings
        all_mailboxes = db.query(VoicemailMailbox).all()
        write_voicemail_config(all_mailboxes, smtp_settings)
        reload_voicemail()
        logger.info(f"Voicemail config generated with {len(all_mailboxes)} mailboxes")
    finally:
        db.close()

    # Load Home Assistant settings from DB
    try:
        from auth import update_ha_api_key
        ha_settings = {}
        for key in ["ha_enabled", "ha_api_key", "mqtt_broker", "mqtt_port", "mqtt_user", "mqtt_password"]:
            s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            ha_settings[key] = s.value if s else ""

        if ha_settings.get("ha_api_key"):
            update_ha_api_key(ha_settings["ha_api_key"])
            logger.info("HA API key loaded from DB")

        if ha_settings.get("ha_enabled") == "true" and ha_settings.get("mqtt_broker"):
            mqtt_publisher.reconfigure(
                broker=ha_settings["mqtt_broker"],
                port=int(ha_settings.get("mqtt_port") or 1883),
                user=ha_settings.get("mqtt_user", ""),
                password=ha_settings.get("mqtt_password", ""),
            )
            logger.info(f"MQTT configured from DB: {ha_settings['mqtt_broker']}")
    except Exception as e:
        logger.warning(f"Failed to load HA settings from DB: {e}")

    # Initialize AMI client
    ami_client = AsteriskAMIClient()
    
    # Build AMI proxy and notify all modules that need it
    ami_proxy = AMIProxy(ami_client)
    await module_registry.startup(ami_proxy)
    
    # Connect MQTT publisher if not already configured from DB settings
    if not mqtt_publisher.connected and mqtt_publisher.enabled:
        mqtt_publisher.connect()

    # Start AMI connection in background
    asyncio.create_task(ami_client.connect())

    # Wait a bit for AMI to connect
    await asyncio.sleep(2)

    logger.info("Backend startup complete")

    # ------------------------------------------------------------------
    # Optional: secondary server that also serves the frontend SPA.
    # Controlled by FRONTEND_PORT env var (default 80).  Set to 0 to disable.
    # ------------------------------------------------------------------
    class _NoSignalServer(uvicorn.Server):
        """Uvicorn server variant that skips process-level signal handlers.

        Used for the secondary frontend server so it does not conflict with
        the primary server's signal handling.
        """

        def install_signal_handlers(self) -> None:
            pass

    frontend_server: Optional[_NoSignalServer] = None
    frontend_task: Optional[asyncio.Task] = None

    frontend_port = int(os.getenv("FRONTEND_PORT", "80"))
    if frontend_port:
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=frontend_port,
            log_level="info",
            log_config=None,
        )
        frontend_server = _NoSignalServer(config)
        frontend_task = asyncio.create_task(frontend_server.serve())
        logger.info("Frontend server started on port %d", frontend_port)

    yield

    # Shutdown frontend server first
    if frontend_server is not None:
        frontend_server.should_exit = True
        if frontend_task is not None:
            try:
                await asyncio.wait_for(frontend_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Frontend server did not shut down cleanly; cancelling task")
                frontend_task.cancel()
    
    # Shutdown
    logger.info("Shutting down backend...")
    await module_registry.shutdown()
    mqtt_publisher.disconnect()
    if ami_client:
        await ami_client.disconnect()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Asterisk PBX GUI API",
    description="REST API for Asterisk PBX Management",
    version=VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire all module routers into the app via the module registry.
module_registry.wire_routes(app)

# Wire static file hosting and the SPA catch-all.  This MUST be the last
# route registration call so that the ``/{full_path:path}`` catch-all does
# not shadow any real API endpoint defined above.
module_registry.wire_static(app, FRONTEND_DIST_DIR)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
