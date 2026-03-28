from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_admin
from app.models import FlightSite, PilotFlight, User
from app.schemas import FlightSiteCreate, FlightSiteRescanResponse, FlightSiteResponse, FlightSiteScanIgcResponse, FlightSiteUpdate
from app.services.logbook import rescan_unmatched_flights_for_sites, scan_igc_for_new_sites

router = APIRouter(prefix="/api/admin/sites", tags=["sites"])


def _site_or_404(session: Session, site_id: int) -> FlightSite:
    site = session.get(FlightSite, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


@router.get("", response_model=list[FlightSiteResponse])
def list_sites(_: User = Depends(require_admin), session: Session = Depends(get_session)) -> list[FlightSiteResponse]:
    sites = session.scalars(select(FlightSite).order_by(FlightSite.name.asc(), FlightSite.id.asc())).all()
    return [FlightSiteResponse.model_validate(site) for site in sites]


@router.post("", response_model=FlightSiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: FlightSiteCreate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> FlightSiteResponse:
    site = FlightSite(
        name=payload.name.strip(),
        city_state=payload.city_state.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_active=payload.is_active,
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    return FlightSiteResponse.model_validate(site)


@router.patch("/{site_id}", response_model=FlightSiteResponse)
def update_site(
    site_id: int,
    payload: FlightSiteUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> FlightSiteResponse:
    site = _site_or_404(session, site_id)
    site.name = payload.name.strip()
    site.city_state = payload.city_state.strip()
    site.latitude = payload.latitude
    site.longitude = payload.longitude
    site.is_active = payload.is_active
    session.add(site)
    session.commit()
    session.refresh(site)
    return FlightSiteResponse.model_validate(site)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: int, _: User = Depends(require_admin), session: Session = Depends(get_session)) -> None:
    _site_or_404(session, site_id)
    session.execute(
        update(PilotFlight)
        .where(PilotFlight.site_id == site_id)
        .values(site_id=None)
    )
    session.execute(FlightSite.__table__.delete().where(FlightSite.id == site_id))
    session.commit()


@router.post("/rescan-flights", response_model=FlightSiteRescanResponse)
def rescan_flights_for_site_match(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> FlightSiteRescanResponse:
    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    return FlightSiteRescanResponse(
        scanned_count=result.scanned_count,
        matched_count=result.matched_count,
        unmatched_count=result.unmatched_count,
    )


@router.post("/scan-igc", response_model=FlightSiteScanIgcResponse)
def scan_igc_for_sites(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> FlightSiteScanIgcResponse:
    """Scan all IGC files for unique takeoff locations.

    Creates new FlightSite entries for takeoff clusters that don't match
    any existing site.  City/state is looked up via reverse geocoding.
    The flight_count field is updated for all sites (existing and new).
    """
    result = scan_igc_for_new_sites(session)
    session.commit()
    return FlightSiteScanIgcResponse(
        new_sites_created=result.new_sites_created,
        flights_matched=result.flights_matched,
        total_igc_scanned=result.total_igc_scanned,
        sites=[FlightSiteResponse.model_validate(s) for s in result.sites],
    )
