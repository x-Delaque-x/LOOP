"""
Address Mapper - Links known location_name strings to physical street addresses.
"""
import logging
from sqlalchemy import text

log = logging.getLogger("enrichment.addresses")

# Known RI locations and their street addresses
ADDRESS_MAP = {
    # Libraries
    "North Kingstown Free Library": "100 Boone St, North Kingstown, RI 02852",
    "South Kingstown Public Library": "1057 Kingstown Rd, Peace Dale, RI 02879",
    "Cranston Public Library": "140 Sockanosset Cross Rd, Cranston, RI 02920",
    "Providence Public Library": "150 Empire St, Providence, RI 02903",
    "Warwick Public Library": "600 Sandy Ln, Warwick, RI 02889",
    "East Greenwich Free Library": "82 Peirce St, East Greenwich, RI 02818",
    "Coventry Public Library": "1672 Flat River Rd, Coventry, RI 02816",
    "West Warwick Public Library": "1043 Main St, West Warwick, RI 02893",
    "Narragansett Public Library": "35 Kingston Rd, Narragansett, RI 02882",
    "Barrington Public Library": "281 County Rd, Barrington, RI",
    "East Providence Public Library": "41 Grove Ave, East Providence, RI 02914",
    "Cumberland Public Library": "1464 Diamond Hill Rd, Cumberland, RI 02864",
    "North Providence Union Free Library": "1810 Mineral Spring Ave, North Providence, RI 02904",
    "Pawtucket Public Library": "13 Summer St, Pawtucket, RI 02860",
    "Woonsocket Harris Public Library": "303 Clinton St, Woonsocket, RI 02895",
    "Westerly Public Library": "44 Broad St, Westerly, RI 02891",
    "Smithfield Public Library": "1 William J Hawkins Jr Trail, Greenville, RI 02828",
    "Johnston Public Library": "1059 Hartford Ave, Johnston, RI 02919",
    "Lincoln Public Library": "145 Old River Rd, Lincoln, RI 02865",
    "Middletown Public Library": "700 W Main Rd, Middletown, RI 02842",
    "Newport Public Library": "300 Spring St, Newport, RI 02840",
    "Tiverton Public Library": "34 Roosevelt Ave, Tiverton, RI 02878",
    "Bristol (Rogers Free Library)": "525 Hope St, Bristol, RI 02809",
    "Exeter Public Library": "773 Ten Rod Rd, Exeter, RI 02822",
    # Recreation Departments
    "North Kingstown Recreation": "55 Callahan Rd, North Kingstown, RI 02852",
    "South Kingstown Recreation": "30 St Dominic Rd, Wakefield, RI 02879",
    "Warwick Recreation": "3259 Post Rd, Warwick, RI 02886",
    "Cranston Recreation": "1070 Cranston St, Cranston, RI 02920",
    "East Greenwich Recreation": "1127 Frenchtown Rd, East Greenwich, RI 02818",
    "Coventry Recreation": "40 Wood St, Coventry, RI 02816",
    "Narragansett Recreation": "53 Mumford Rd, Narragansett, RI 02882",
    "Barrington Recreation": "283 County Rd, Barrington, RI",
    "Cumberland Recreation": "3140 Diamond Hill Rd, Cumberland, RI 02864",
    "Lincoln Recreation": "652 George Washington Hwy, Lincoln, RI 02865",
    "East Providence Recreation": "50 Hunts Mills Rd, East Providence, RI 02916",
    "Johnston Recreation": "1583 Hartford Ave, Johnston, RI 02919",
    "Portsmouth Public Library": "2658 E Main Rd, Portsmouth, RI 02871",
    "Richmond Public Library": "1 Beach St, Richmond, RI 02898",
    "Bristol Recreation": "2 Luther Ave, Bristol, RI 02809",
    "Burrillville Recreation": "105 Harrisville Main St, Harrisville, RI 02830",
}


def update_addresses(session):
    """
    For every row in golden_events where address IS NULL,
    look up location_name in ADDRESS_MAP and set the address.
    """
    result = session.execute(
        text("SELECT DISTINCT location_name FROM golden_events WHERE address IS NULL")
    )
    unmapped = []
    updated = 0

    for row in result:
        location_name = row[0]
        if not location_name:
            continue

        address = ADDRESS_MAP.get(location_name)
        if address:
            session.execute(
                text("UPDATE golden_events SET address = :addr WHERE location_name = :loc AND address IS NULL"),
                {"addr": address, "loc": location_name}
            )
            updated += 1
            log.info(f"  Mapped: {location_name} -> {address}")
        else:
            unmapped.append(location_name)

    if unmapped:
        log.warning(f"  Unmapped locations (add to ADDRESS_MAP): {unmapped}")

    log.info(f"  Updated {updated} location(s)")
