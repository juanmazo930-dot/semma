"""
============================================================
SEMMA BACKEND — El cerebro del interruptor vivo
============================================================
Qué hace este servidor:

1. USUARIOS      → registro y login seguros (la contraseña se guarda
                   como hash, nunca en texto plano)
2. BÓVEDA        → guarda el blob CIFRADO que crea el navegador.
                   El servidor nunca ve el contenido (conocimiento cero)
3. GUARDIANES    → los beneficiarios que elige el usuario
4. CHECK-INS     → el usuario confirma que está bien; si deja de
                   responder, arranca el protocolo de escalada
5. ESCALADA      → recordatorio → aviso urgente → liberación a guardianes

Para ejecutarlo en tu ordenador:
    pip install -r requirements.txt
    uvicorn main:app --reload
Luego abre http://localhost:8000/docs  ← documentación interactiva gratis
============================================================
"""

import os
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (create_engine, Column, Integer, String, Text,
                        DateTime, ForeignKey, select)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ------------------------------------------------------------
# CONFIGURACIÓN — todo por variables de entorno (nunca en el código)
# ------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./semma.db")
JWT_SECRET = os.getenv("JWT_SECRET", "cambia-esto-en-produccion-" + "x" * 32)
JWT_HOURS = 24 * 7  # la sesión dura 7 días
ADMIN_KEY = os.getenv("ADMIN_KEY", "cambia-esta-clave-admin")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")   # para emails reales (resend.com, gratis)
FROM_EMAIL = os.getenv("FROM_EMAIL", "Semma <onboarding@resend.dev>")
APP_URL = os.getenv("APP_URL", "https://juanmazo930-dot.github.io/semma")

# Render/Neon dan URLs "postgres://" pero SQLAlchemy quiere "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

# ------------------------------------------------------------
# TABLAS DE LA BASE DE DATOS
# ------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)   # hash, jamás la contraseña
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # --- configuración del interruptor vivo ---
    checkin_days = Column(Integer, default=30)      # cada cuántos días verificamos
    last_checkin = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    escalation_stage = Column(Integer, default=0)
    # 0 = todo bien | 1 = recordatorio enviado | 2 = aviso urgente | 3 = liberado


class Vault(Base):
    __tablename__ = "vaults"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    # El blob cifrado tal cual llega del navegador. Ilegible para nosotros.
    encrypted_blob = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Guardian(Base):
    __tablename__ = "guardians"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), nullable=False)


Base.metadata.create_all(engine)

# ------------------------------------------------------------
# SEGURIDAD DE CONTRASEÑAS (PBKDF2, igual que hicimos en el navegador)
# ------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest_hex = stored.split("$")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210_000)
    # compare_digest evita ataques de temporización (buena práctica)
    return hmac.compare_digest(candidate.hex(), digest_hex)


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": time.time() + JWT_HOURS * 3600}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ------------------------------------------------------------
# EMAILS — con Resend (gratis 100/día). Sin clave: se imprimen en consola.
# ------------------------------------------------------------
def send_email(to: str, subject: str, body: str) -> None:
    if not RESEND_API_KEY:
        print(f"\n[EMAIL SIMULADO] Para: {to}\nAsunto: {subject}\n{body}\n")
        return
    import httpx
    httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": FROM_EMAIL, "to": [to], "subject": subject, "text": body},
        timeout=15,
    )


# ------------------------------------------------------------
# LA APP
# ------------------------------------------------------------
app = FastAPI(
    title="Semma API",
    description="El interruptor vivo: custodia cifrada y entrega de legado digital.",
    version="0.1.0",
)

# CORS: permite que tu web en GitHub Pages hable con este servidor
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # al lanzar en serio, restringe a tu dominio
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    """Lee el token 'Bearer xxx' y devuelve el usuario. Protege los endpoints."""
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
        if not user:
            raise ValueError
        return user
    except Exception:
        raise HTTPException(401, "Sesión inválida o caducada")


# ------------------------------------------------------------
# MODELOS DE ENTRADA (validación automática con Pydantic)
# ------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VaultIn(BaseModel):
    encrypted_blob: str  # el JSON cifrado que produce app.html


class GuardianIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr


class SettingsIn(BaseModel):
    checkin_days: int = Field(ge=7, le=365)


# ------------------------------------------------------------
# ENDPOINTS: CUENTAS
# ------------------------------------------------------------
@app.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Ese email ya está registrado")
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    return {"token": create_token(user.id), "email": user.email}


@app.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email o contraseña incorrectos")
    return {"token": create_token(user.id), "email": user.email}


# ------------------------------------------------------------
# ENDPOINTS: BÓVEDA (conocimiento cero — solo guardamos el blob cifrado)
# ------------------------------------------------------------
@app.put("/vault")
def save_vault(data: VaultIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vault = db.scalar(select(Vault).where(Vault.user_id == user.id))
    if vault:
        vault.encrypted_blob = data.encrypted_blob
        vault.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Vault(user_id=user.id, encrypted_blob=data.encrypted_blob))
    db.commit()
    return {"status": "saved"}


@app.get("/vault")
def get_vault(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vault = db.scalar(select(Vault).where(Vault.user_id == user.id))
    if not vault:
        raise HTTPException(404, "Aún no hay bóveda guardada")
    return {"encrypted_blob": vault.encrypted_blob, "updated_at": str(vault.updated_at)}


# ------------------------------------------------------------
# ENDPOINTS: GUARDIANES
# ------------------------------------------------------------
@app.post("/guardians")
def add_guardian(data: GuardianIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = len(db.scalars(select(Guardian).where(Guardian.user_id == user.id)).all())
    if count >= 5:
        raise HTTPException(400, "Máximo 5 guardianes")
    g = Guardian(user_id=user.id, name=data.name, email=data.email.lower())
    db.add(g)
    db.commit()
    return {"id": g.id, "name": g.name, "email": g.email}


@app.get("/guardians")
def list_guardians(user: User = Depends(current_user), db: Session = Depends(get_db)):
    gs = db.scalars(select(Guardian).where(Guardian.user_id == user.id)).all()
    return [{"id": g.id, "name": g.name, "email": g.email} for g in gs]


@app.delete("/guardians/{guardian_id}")
def delete_guardian(guardian_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.get(Guardian, guardian_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404, "Guardián no encontrado")
    db.delete(g)
    db.commit()
    return {"status": "deleted"}


# ------------------------------------------------------------
# ENDPOINTS: EL INTERRUPTOR VIVO
# ------------------------------------------------------------
@app.post("/checkin")
def checkin(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """El usuario dice 'sigo aquí'. Reinicia el reloj y cancela cualquier escalada."""
    user.last_checkin = datetime.now(timezone.utc)
    user.escalation_stage = 0
    db.commit()
    return {"status": "alive", "next_check_due_in_days": user.checkin_days}


@app.put("/settings")
def update_settings(data: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.checkin_days = data.checkin_days
    db.commit()
    return {"checkin_days": user.checkin_days}


@app.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    last = user.last_checkin
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days_since = (datetime.now(timezone.utc) - last).days
    guardians = len(db.scalars(select(Guardian).where(Guardian.user_id == user.id)).all())
    has_vault = db.scalar(select(Vault).where(Vault.user_id == user.id)) is not None
    return {
        "email": user.email,
        "checkin_days": user.checkin_days,
        "days_since_checkin": days_since,
        "escalation_stage": user.escalation_stage,
        "guardians": guardians,
        "has_vault": has_vault,
    }


# ------------------------------------------------------------
# EL PROTOCOLO DE ESCALADA — el corazón de Semma
# Lo ejecuta un cron externo (cron-job.org) una vez al día.
# ------------------------------------------------------------
@app.post("/admin/run-checks")
def run_checks(x_admin_key: str = Header(...), db: Session = Depends(get_db)):
    if not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, "Clave de administrador incorrecta")

    now = datetime.now(timezone.utc)
    actions = []

    for user in db.scalars(select(User)).all():
        last = user.last_checkin
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        overdue_days = (now - last).days - user.checkin_days

        # ETAPA 1: se pasó la fecha → recordatorio amable
        if overdue_days >= 0 and user.escalation_stage == 0:
            send_email(
                user.email,
                "Semma — ¿Sigues ahí? 💚",
                f"Hola,\n\nHace {user.checkin_days}+ días que no confirmas que estás bien.\n"
                f"Entra y pulsa 'Sigo aquí': {APP_URL}/app.html\n\n"
                "Si no respondes en 7 días, enviaremos un aviso urgente.\n— Semma",
            )
            user.escalation_stage = 1
            actions.append(f"recordatorio → {user.email}")

        # ETAPA 2: 7 días más sin respuesta → aviso urgente
        elif overdue_days >= 7 and user.escalation_stage == 1:
            send_email(
                user.email,
                "Semma — AVISO URGENTE: tu protocolo de legado se activará pronto",
                f"Hola,\n\nSeguimos sin noticias tuyas. Si no confirmas en 7 días,\n"
                f"notificaremos a tus guardianes según tus instrucciones.\n"
                f"Confirma aquí: {APP_URL}/app.html\n— Semma",
            )
            user.escalation_stage = 2
            actions.append(f"aviso urgente → {user.email}")

        # ETAPA 3: 14 días sin respuesta → liberar a los guardianes
        elif overdue_days >= 14 and user.escalation_stage == 2:
            guardians = db.scalars(select(Guardian).where(Guardian.user_id == user.id)).all()
            for g in guardians:
                send_email(
                    g.email,
                    f"Semma — {user.email} te ha dejado su legado digital",
                    f"Hola {g.name},\n\n"
                    f"{user.email} te designó como guardián de su legado digital.\n"
                    f"No ha respondido a nuestras verificaciones durante un periodo\n"
                    f"prolongado, por lo que su protocolo se ha activado.\n\n"
                    f"Accede a la bóveda aquí: {APP_URL}/app.html\n"
                    f"Necesitarás la clave de desbloqueo que esa persona compartió\n"
                    f"contigo en vida. Semma no la conoce ni puede recuperarla.\n\n"
                    "Con cariño,\n— El equipo de Semma",
                )
            user.escalation_stage = 3
            actions.append(f"LIBERADO → {len(guardians)} guardianes de {user.email}")

    db.commit()
    return {"checked_at": str(now), "actions": actions or ["sin cambios"]}


# ------------------------------------------------------------
# SOLO PARA PRUEBAS — simula que 
