"""Checks for generate.py. Run: py -3 check_generate.py"""

import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import generate

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "wp-templates"
REAL_MODELS = ROOT / "wp-models"
PLACEHOLDERS = generate.PLACEHOLDERS


def fail(message):
    raise SystemExit(message)


def read_xml(path):
    return ET.parse(path).getroot()


def assert_no_placeholders(folder):
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".meta", ".lua"}:
            text = path.read_text(encoding="utf-8")
            for token in PLACEHOLDERS:
                if token in text:
                    fail(f"{path} still has {token}")


def make_model(folder, stem, extra=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.ydr").write_bytes(b"ydr")
    (folder / f"{stem}.ytd").write_bytes(b"ytd")
    if extra:
        (folder / f"{extra}.ydr").write_bytes(b"ydr")


def test_separate(tmp):
    out = tmp / "out-separate"
    written = generate.generate(
        "separate",
        "ignored",
        [("WEAPON_BAT", "WEAPON_BASEBALL_DX", "weapon_baseball_dx")],
        TEMPLATES,
        REAL_MODELS,
        out,
    )
    resource = written[0]
    if resource.name != "WEAPON_BASEBALL_DX":
        fail("separate resource name")
    weapon = read_xml(resource / "meta" / "weapon.meta")
    info = weapon.find("./Infos/Item/Infos/Item[@type='CWeaponInfo']")
    if info is None:
        info = weapon.find(".//Item[@type='CWeaponInfo']")
    if info.findtext("Name") != "WEAPON_BASEBALL_DX":
        fail("weapon name")
    if info.findtext("Model") != "weapon_baseball_dx":
        fail("weapon model")
    if info.findtext("Slot") != "SLOT_WEAPON_BASEBALL_DX":
        fail("slot")
    orders = [node.get("value") for node in weapon.findall(".//OrderNumber")]
    if not orders or any(not value.isdigit() for value in orders):
        fail(f"order numbers {orders}")
    if len(set(orders)) != 1 or orders[0] != "10000":
        fail(f"expected order 10000, got {orders}")
    arch = read_xml(resource / "meta" / "weaponarchetypes.meta")
    if arch.findtext("./InitDatas/Item/modelName") != "weapon_baseball_dx":
        fail("archetype model")
    stream = resource / "stream"
    if not (stream / "weapon_baseball_dx.ydr").is_file() or not (stream / "weapon_baseball_dx.ytd").is_file():
        fail("stream files missing")
    manifest = (resource / "fxmanifest.lua").read_text(encoding="utf-8")
    if "weaponcomponents.meta" in manifest:
        fail("manifest lists missing components file")
    if "PED_PERSONALITY_FILE" not in manifest or "WEAPONINFO_FILE" not in manifest:
        fail("manifest data files")
    assert_no_placeholders(resource)

    hammer = generate.generate(
        "separate",
        "ignored",
        [("WEAPON_HAMMER", "WEAPON_HAMMER_DX", "weapon_baseball_dx")],
        TEMPLATES,
        REAL_MODELS,
        out,
    )[0]
    hammer_manifest = (hammer / "fxmanifest.lua").read_text(encoding="utf-8")
    if "pedpersonality.meta" in hammer_manifest:
        fail("hammer manifest should omit pedpersonality")
    if (out / ".next-order").read_text(encoding="utf-8").strip() != "10002":
        fail("order counter")


def test_pack(tmp):
    models = tmp / "models"
    make_model(models / "weapon_baseball_dx", "weapon_baseball_dx")
    make_model(models / "w_pi_revolver_test", "w_pi_revolver_test", extra="extra_comp")
    out = tmp / "out-pack"
    resource = generate.generate(
        "pack",
        "weapons_pack",
        [
            ("WEAPON_BAT", "WEAPON_BASEBALL_DX", "weapon_baseball_dx"),
            ("WEAPON_REVOLVER", "WEAPON_REV_TEST", "w_pi_revolver_test"),
        ],
        TEMPLATES,
        models,
        out,
    )[0]
    meta = resource / "meta"
    names = {path.name for path in meta.iterdir()}
    if names != {"weapon.meta", "weaponanimations.meta", "weaponarchetypes.meta", "pedpersonality.meta"}:
        fail(f"pack meta files {names}")
    weapon = read_xml(meta / "weapon.meta")
    weapon_names = [node.text for node in weapon.findall(".//Item[@type='CWeaponInfo']/Name")]
    if weapon_names != ["WEAPON_BASEBALL_DX", "WEAPON_REV_TEST"]:
        fail(f"packed weapon names {weapon_names}")
    orders = {node.get("value") for node in weapon.findall(".//OrderNumber")}
    if orders != {"10000", "10001"}:
        fail(f"packed orders {orders}")
    anim = read_xml(meta / "weaponanimations.meta")
    defaults = anim.findall("./WeaponAnimationsSets/Item[@key='Default']")
    if len(defaults) != 1:
        fail(f"Default blocks {len(defaults)}")
    keys = [item.get("key") for item in defaults[0].findall("./WeaponAnimations/Item")]
    if "WEAPON_BASEBALL_DX" not in keys or "WEAPON_REV_TEST" not in keys:
        fail(f"animation keys {keys}")
    ped = (meta / "pedpersonality.meta").read_text(encoding="utf-8")
    if "WEAPON_BASEBALL_DX" not in ped or "WEAPON_REV_TEST" not in ped:
        fail("pedpersonality missing a weapon")
    arch_names = [node.text for node in read_xml(meta / "weaponarchetypes.meta").findall(".//modelName")]
    if arch_names != ["weapon_baseball_dx", "w_pi_revolver_test", "extra_comp"]:
        fail(f"archetypes {arch_names}")
    if not (resource / "stream" / "extra_comp.ydr").is_file():
        fail("extra model was not copied")
    manifest = (resource / "fxmanifest.lua").read_text(encoding="utf-8")
    if manifest.count("WEAPON_ANIMATIONS_FILE") != 1 or "weaponcomponents" in manifest:
        fail("pack manifest")
    assert_no_placeholders(resource)


def test_errors(tmp):
    out = tmp / "out-errors"
    try:
        generate.generate(
            "separate",
            "x",
            [("WEAPON_BAT", "WEAPON_MISSING", "no_such_model")],
            TEMPLATES,
            REAL_MODELS,
            out,
        )
    except generate.GenerateError as error:
        if "no_such_model" not in str(error):
            fail(f"unexpected missing-model error: {error}")
    else:
        fail("missing model should fail")
    models = tmp / "err-models"
    make_model(models / "weapon_baseball_dx", "weapon_baseball_dx")
    try:
        generate.generate(
            "pack",
            "dup",
            [
                ("WEAPON_BAT", "WEAPON_SAME", "weapon_baseball_dx"),
                ("WEAPON_POOLCUE", "WEAPON_SAME", "weapon_baseball_dx"),
            ],
            TEMPLATES,
            models,
            out,
        )
    except generate.GenerateError as error:
        if "ซ้ำ" not in str(error):
            fail(f"unexpected duplicate error: {error}")
    else:
        fail("duplicate name should fail")
    if (out / ".next-order").exists():
        fail("failed run advanced the order counter")


def test_slot_templates(tmp):
    models = tmp / "slot-models"
    make_model(models / "weapon_baseball_dx", "weapon_baseball_dx")
    out = tmp / "out-slots"
    for template, ingame in (
        ("WEAPON_GOLFCLUB", "WEAPON_GOLF_DX"),
        ("WEAPON_NIGHTSTICK", "WEAPON_STICK_DX"),
        ("WEAPON_ACIDPACKAGE", "WEAPON_ACID_DX"),
    ):
        resource = generate.generate(
            "separate",
            ingame,
            [(template, ingame, "weapon_baseball_dx")],
            TEMPLATES,
            models,
            out,
        )[0]
        slot = read_xml(resource / "meta" / "weapon.meta").find(".//Item[@type='CWeaponInfo']/Slot").text
        if slot != f"SLOT_{ingame}":
            fail(f"{template} slot is {slot}")
        assert_no_placeholders(resource)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="wpmod-check-"))
    try:
        test_separate(tmp)
        test_pack(tmp)
        test_errors(tmp)
        test_slot_templates(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ok")


if __name__ == "__main__":
    main()
