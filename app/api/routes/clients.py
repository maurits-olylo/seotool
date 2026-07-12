from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.client import Client
from app.models.user import ClientMembership
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate
from app.services.authorization import (
    accessible_client_ids,
    require_client_access,
    require_global_role,
)

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Client:
    require_global_role(principal, "superuser", "admin")
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, key, value)
    db.commit()
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
