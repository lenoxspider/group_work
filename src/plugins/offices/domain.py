"""Offices domain - the positions of state."""

MAGISTRATE = "magistrate"
TREASURER = "treasurer"
FRONT_MAN = "front_man"

OFFICES = (MAGISTRATE, TREASURER, FRONT_MAN)

OFFICE_LABELS = {
    MAGISTRATE: "Magistrate",
    TREASURER: "Treasurer",
    FRONT_MAN: "Front Man",
}

# The Discord role each office maps to (created by /setup).
OFFICE_ROLE = {
    MAGISTRATE: "Magistrate",
    TREASURER: "Treasurer",
    FRONT_MAN: "Front Man",
}

OFFICE_DUTY = {
    MAGISTRATE: "Rules the court - closes cases and carries out sentences.",
    TREASURER: "Keeps the coffers - the only one who may propose spending from the treasury.",
    FRONT_MAN: "Hosts the Games.",
}
