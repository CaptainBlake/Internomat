"""Canonical CS2 weapon catalog and alias mapping for stat tracking."""

# Canonical gameplay-level weapon identifiers used by analytics tables.
CS2_CANONICAL_WEAPONS = [
    # Pistols
    "glock-18",
    "usp-s",
    "p2000",
    "dual-berettas",
    "p250",
    "five-seven",
    "tec-9",
    "cz75-auto",
    "desert-eagle",
    "r8-revolver",
    # SMGs
    "mac-10",
    "mp9",
    "mp7",
    "mp5-sd",
    "ump-45",
    "p90",
    "pp-bizon",
    # Heavy
    "nova",
    "xm1014",
    "mag-7",
    "sawed-off",
    "m249",
    "negev",
    # Rifles
    "galil-ar",
    "famas",
    "ak-47",
    "m4a4",
    "m4a1-s",
    "sg-553",
    "aug",
    "awp",
    "ssg-08",
    "g3sg1",
    "scar-20",
    # Utility / equipment that appears in demo weapon columns
    "zeus-x27",
    "knife",
    "c4",
    "he-grenade",
    "flashbang",
    "smoke-grenade",
    "molotov",
    "incendiary-grenade",
    "decoy-grenade",
]


# Raw parser/demo tokens mapped to canonical weapon identifiers.
CS2_WEAPON_ALIASES = {
    # Prefix/noise variants
    "weapon_glock": "glock-18",
    "weapon_usp_silencer": "usp-s",
    "weapon_hkp2000": "p2000",
    "weapon_p2000": "p2000",
    "weapon_elite": "dual-berettas",
    "weapon_fiveseven": "five-seven",
    "weapon_tec9": "tec-9",
    "weapon_cz75a": "cz75-auto",
    "weapon_deagle": "desert-eagle",
    "weapon_revolver": "r8-revolver",
    "weapon_mac10": "mac-10",
    "weapon_mp5sd": "mp5-sd",
    "weapon_ump45": "ump-45",
    "weapon_bizon": "pp-bizon",
    "weapon_mag7": "mag-7",
    "weapon_sawedoff": "sawed-off",
    "weapon_galilar": "galil-ar",
    "weapon_m4a1": "m4a1-s",
    "weapon_m4a1_silencer": "m4a1-s",
    "weapon_sg556": "sg-553",
    "weapon_ssg08": "ssg-08",
    "weapon_scar20": "scar-20",
    "weapon_taser": "zeus-x27",
    "weapon_zeus": "zeus-x27",
    "weapon_zeusx27": "zeus-x27",
    "weapon_knife": "knife",
    "weapon_bayonet": "knife",
    "weapon_c4": "c4",
    "weapon_hegrenade": "he-grenade",
    "weapon_flashbang": "flashbang",
    "weapon_smokegrenade": "smoke-grenade",
    "weapon_molotov": "molotov",
    "weapon_incgrenade": "incendiary-grenade",
    "weapon_decoy": "decoy-grenade",
    # Common plain names
    "glock": "glock-18",
    "glock18": "glock-18",
    "usp_silencer": "usp-s",
    "hkp2000": "p2000",
    "elite": "dual-berettas",
    "fiveseven": "five-seven",
    "tec9": "tec-9",
    "cz75a": "cz75-auto",
    "deagle": "desert-eagle",
    "revolver": "r8-revolver",
    "mac10": "mac-10",
    "mp5sd": "mp5-sd",
    "ump45": "ump-45",
    "bizon": "pp-bizon",
    "mag7": "mag-7",
    "sawedoff": "sawed-off",
    "galilar": "galil-ar",
    "m4a1": "m4a1-s",
    "m4a1_silencer": "m4a1-s",
    "sg556": "sg-553",
    "ssg08": "ssg-08",
    "scar20": "scar-20",
    "taser": "zeus-x27",
    "zeus": "zeus-x27",
    "zeusx27": "zeus-x27",
    "bayonet": "knife",
    "hegrenade": "he-grenade",
    "smokegrenade": "smoke-grenade",
    "incgrenade": "incendiary-grenade",
}


# Knife cosmetic variants all collapse to canonical knife.
CS2_KNIFE_VARIANT_ALIASES = [
    "bayonet",
    "knife_bayonet",
    "weapon_knife_bayonet",
    "weapon_knife_t",
    "weapon_knife_css",
    "weapon_knife_karambit",
    "weapon_knife_m9_bayonet",
    "weapon_knife_butterfly",
    "weapon_knife_flip",
    "weapon_knife_gut",
    "weapon_knife_tactical",
    "weapon_knife_falchion",
    "weapon_knife_survival_bowie",
    "weapon_knife_push",
    "weapon_knife_ursus",
    "weapon_knife_gypsy_jackknife",
    "weapon_knife_stiletto",
    "weapon_knife_widowmaker",
    "weapon_knife_canis",
    "weapon_knife_cord",
    "weapon_knife_outdoor",
    "weapon_knife_skeleton",
    "weapon_knife_kukri",
]


def iter_seed_weapon_rows():
    """Rows for weapon_dim seed insert."""
    for weapon in CS2_CANONICAL_WEAPONS:
        category = "utility"
        if weapon in {
            "glock-18", "usp-s", "p2000", "dual-berettas", "p250", "five-seven", "tec-9", "cz75-auto", "desert-eagle", "r8-revolver"
        }:
            category = "pistol"
        elif weapon in {"mac-10", "mp9", "mp7", "mp5-sd", "ump-45", "p90", "pp-bizon"}:
            category = "smg"
        elif weapon in {"nova", "xm1014", "mag-7", "sawed-off", "m249", "negev"}:
            category = "heavy"
        elif weapon in {"galil-ar", "famas", "ak-47", "m4a4", "m4a1-s", "sg-553", "aug", "awp", "ssg-08", "g3sg1", "scar-20"}:
            category = "rifle"
        elif weapon == "knife":
            category = "melee"

        yield (weapon, weapon, category, "seed-cs2")


def iter_seed_alias_rows():
    """Rows for weapon_alias seed insert."""
    for raw, canonical in CS2_WEAPON_ALIASES.items():
        yield (raw, canonical, "seed-cs2")

    for raw in CS2_KNIFE_VARIANT_ALIASES:
        yield (raw, "knife", "seed-cs2")


def normalize_weapon_name(raw_weapon):
    """Normalize parser/raw weapon tokens to canonical weapon ids."""
    raw = str(raw_weapon or "").strip().lower()
    if not raw:
        return ""

    base = raw.replace("weapon_", "")
    base = base.replace("item_", "")
    base = base.replace(" ", "_")

    if raw in CS2_WEAPON_ALIASES:
        return CS2_WEAPON_ALIASES[raw]
    if base in CS2_WEAPON_ALIASES:
        return CS2_WEAPON_ALIASES[base]

    if raw in CS2_KNIFE_VARIANT_ALIASES or base.startswith("knife_"):
        return "knife"

    if base in {"ak47", "ak-47"}:
        return "ak-47"
    if base in {"m4a1_silencer", "m4a1-s"}:
        return "m4a1-s"
    if base in {"usp_silencer", "usp-s"}:
        return "usp-s"
    if base in {"sg556", "sg-553"}:
        return "sg-553"
    if base in {"ssg08", "ssg-08"}:
        return "ssg-08"
    if base in {"scar20", "scar-20"}:
        return "scar-20"
    if base in {"galilar", "galil-ar"}:
        return "galil-ar"
    if base in {"ump45", "ump-45"}:
        return "ump-45"
    if base in {"mac10", "mac-10"}:
        return "mac-10"
    if base in {"mp5sd", "mp5-sd"}:
        return "mp5-sd"
    if base in {"fiveseven", "five-seven"}:
        return "five-seven"
    if base in {"cz75a", "cz75-auto"}:
        return "cz75-auto"
    if base in {"deagle", "desert-eagle"}:
        return "desert-eagle"
    if base in {"bizon", "pp-bizon"}:
        return "pp-bizon"
    if base in {"hegrenade", "he-grenade"}:
        return "he-grenade"
    if base in {"smokegrenade", "smoke-grenade"}:
        return "smoke-grenade"
    if base in {"incgrenade", "incendiary-grenade"}:
        return "incendiary-grenade"
    if base in {"zeus", "zeusx27", "taser", "zeus-x27"}:
        return "zeus-x27"

    return base.replace("_", "-")
