from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.client import Client
from app.models.user import ClientMembership
from app.models.website import Website, WebsiteSettings
from app.schemas.client import (
    ClientCreate,
    ClientOnboardingCreate,
    ClientOnboardingRead,
    ClientRead,
    ClientUpdate,
)
from app.services.authorization import (
    accessible_client_ids,
    require_client_access,
    require_global_role,
)

router = APIRouter(prefix="/clients", tags=["clients"])


def _ensure_unique_client(
    db: Session,
    name: str,
    internal_reference: str | None,
    *,
    exclude_client_id: UUID | None = None,
) -> None:
    name_query = select(Client.id).where(func.lower(Client.name) == name.lower())
    if exclude_client_id:
        name_query = name_query.where(Client.id != exclude_client_id)
    duplicate = db.scalar(name_query)
    if duplicate:
        raise HTTPException(status_code=409, detail="Er bestaat al een klant met deze naam")
    if internal_reference:
        reference_query = select(Client.id).where(
            Client.internal_reference == internal_reference
        )
        if exclude_client_id:
            reference_query = reference_query.where(Client.id != exclude_client_id)
        if db.scalar(reference_query):
            raise HTTPException(status_code=409, detail="Interne referentie is al in gebruik")


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Client:
    require_global_role(principal, "superuser", "admin")
    _ensure_unique_client(db, payload.name, payload.internal_reference)
    client = Client(**payload.model_dump())
    db.add(client)
    try:
        db.flush()
        if principal.user_id and principal.role != "superuser":
            db.add(ClientMembership(user_id=principal.user_id, client_id=client.id, role="admin"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Client already exists") from exc
    db.refresh(client)
    return client


@router.post("/onboard", response_model=ClientOnboardingRead, status_code=status.HTTP_201_CREATED)
def onboard_client(
    payload: ClientOnboardingCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, Client | Website]:
    require_global_role(principal, "superuser", "admin")
    _ensure_unique_client(db, payload.name, payload.internal_reference)
    client = Client(name=payload.name, internal_reference=payload.internal_reference)
    website = Website(
        client=client,
        name=payload.website_name,
        base_url=str(payload.base_url),
        status="active",
    )
    website.settings = WebsiteSettings()
    db.add(client)
    try:
        db.flush()
        if principal.user_id and principal.role != "superuser":
            db.add(ClientMembership(user_id=principal.user_id, client_id=client.id, role="admin"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Klant of website bestaat al") from exc
    db.refresh(client)
    db.refresh(website)
    return {"client": client, "website": website}


@router.get("", response_model=list[ClientRead])
def list_clients(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[Client]:
    query = select(Client).order_by(Client.name)
    client_ids = accessible_client_ids(db, principal)
    if client_ids is not None:
        query = query.where(Client.id.in_(client_ids))
    return list(db.scalars(query))


def get_client_or_404(client_id: UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/{client_id}", response_model=ClientRead)
def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Client:
    require_client_access(db, principal, client_id)
    return get_client_or_404(client_id, db)


@router.patch("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Client:
    require_client_access(db, principal, client_id, admin=True)
    client = get_client_or_404(client_id, db)
    changes = payload.model_dump(exclude_unset=True)
    _ensure_unique_client(
        db,
        changes.get("name", client.name),
        changes.get("internal_reference", client.internal_reference),
        exclude_client_id=client.id,
    )
    for key, value in changes.items():
        setattr(client, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Klantgegevens zijn al in gebruik") from exc
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Response:
    require_client_access(db, principal, client_id, admin=True)
    db.delete(get_client_or_404(client_id, db))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
