"""Build a ready-to-start FiveM weapon resource from wp-templates and wp-models."""

import copy
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "wp-templates"
MODELS = ROOT / "wp-models"
OUTPUT = ROOT / "output"

NAME_RE = re.compile(r"[A-Z0-9_]+")
RESOURCE_RE = re.compile(r"[A-Za-z0-9_]+")
STREAM_EXT = {".ydr", ".ytd", ".yft"}
ORDER_START = 10000

META_FILES = [
    ("weaponcomponents.meta", "WEAPONCOMPONENTSINFO_FILE"),
    ("weaponarchetypes.meta", "WEAPON_METADATA_FILE"),
    ("weaponanimations.meta", "WEAPON_ANIMATIONS_FILE"),
    ("pedpersonality.meta", "PED_PERSONALITY_FILE"),
    ("weapon.meta", "WEAPONINFO_FILE"),
]
PLACEHOLDERS = (
    "NEW_ORDER_NUMBER_HERE",
    "WEAPON_IN_GAME_NAME_HERE",
    "SLOT_NAME_HERE",
    "WEAPON_MODEL_NAME_HERE",
)


class GenerateError(Exception):
    pass


def list_templates(templates_dir):
    names = []
    for path in sorted(templates_dir.iterdir()):
        if path.is_dir() and (path / "meta").is_dir():
            names.append(path.name)
    return names


def list_models(models_dir):
    names = []
    for path in sorted(models_dir.iterdir()):
        if path.is_dir() and any(f.suffix.lower() == ".ydr" for f in path.iterdir() if f.is_file()):
            names.append(path.name)
    return names


def find_template(templates_dir, name):
    for path in templates_dir.iterdir():
        if path.is_dir() and path.name.lower() == name.lower() and (path / "meta").is_dir():
            return path
    raise GenerateError(f"ไม่พบ template {name}")


def resolve_model(models_dir, model_name):
    want = model_name.lower()
    folder = None
    for path in models_dir.iterdir():
        if path.is_dir() and path.name.lower() == want:
            folder = path
            break
    if folder is None:
        raise GenerateError(f"ไม่พบโฟลเดอร์โมเดล {model_name} ใน wp-models")
    match = None
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() == ".ydr" and path.stem.lower() == want:
            match = path
            break
    if match is None:
        raise GenerateError(f"ไม่พบไฟล์ {model_name}.ydr ใน {folder.name}")
    return folder, match.stem


def read_meta(template_dir):
    meta_dir = template_dir / "meta"
    found = {}
    for filename, _data_type in META_FILES:
        path = meta_dir / filename
        if path.is_file():
            found[filename] = path.read_text(encoding="utf-8")
    if "weapon.meta" not in found or "weaponarchetypes.meta" not in found:
        raise GenerateError(f"{template_dir.name} ไม่มี weapon.meta หรือ weaponarchetypes.meta")
    return found


def fill_text(text, ingame, model, order):
    text = text.replace("NEW_ORDER_NUMBER_HERE", str(order))
    text = text.replace("WEAPON_IN_GAME_NAME_HERE", ingame)
    text = text.replace("SLOT_NAME_HERE", f"SLOT_{ingame}")
    text = text.replace("WEAPON_MODEL_NAME_HERE", model)
    leftover = [token for token in PLACEHOLDERS if token in text]
    if leftover:
        raise GenerateError("แทนที่ placeholder ไม่ครบ: " + ", ".join(leftover))
    return text


def fill_weapon(template_dir, ingame, model, order):
    return {
        filename: fill_text(text, ingame, model, order)
        for filename, text in read_meta(template_dir).items()
    }


def take_orders(output_dir, count):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ".next-order"
    start = ORDER_START
    if path.is_file():
        start = int(path.read_text(encoding="utf-8").strip())
    numbers = list(range(start, start + count))
    return numbers, start + count


def commit_order(output_dir, next_order):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".next-order").write_text(str(next_order), encoding="utf-8")


def write_manifest(resource_dir, meta_names):
    files = []
    data_lines = []
    for filename, data_type in META_FILES:
        if filename not in meta_names:
            continue
        rel = f"meta/{filename}"
        files.append(f'    "{rel}"')
        data_lines.append(f'data_file "{data_type}" "{rel}"')
    body = "\n".join(
        [
            'fx_version "cerulean"',
            "games {",
            '    "gta5"',
            "}",
            "",
            "files {",
            ",\n".join(files),
            "}",
            "",
            *data_lines,
            "",
        ]
    )
    (resource_dir / "fxmanifest.lua").write_text(body, encoding="utf-8", newline="\n")


def write_xml(path, root):
    if hasattr(ET, "indent"):
        ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def copy_stream(model_dir, stream_dir):
    stream_dir.mkdir(parents=True, exist_ok=True)
    stems = []
    for path in sorted(model_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in STREAM_EXT:
            shutil.copy2(path, stream_dir / path.name)
            if path.suffix.lower() == ".ydr":
                stems.append(path.stem)
    return stems


def archetype_names(root):
    return {(item.text or "").strip().lower() for item in root.findall("./InitDatas/Item/modelName")}


def add_archetype(root, model_name):
    if model_name.lower() in archetype_names(root):
        return
    init = root.find("InitDatas")
    if init is None:
        init = ET.SubElement(root, "InitDatas")
    first = init.find("Item")
    if first is not None:
        item = copy.deepcopy(first)
        for tag in ("modelName", "txdName"):
            node = item.find(tag)
            if node is not None:
                node.text = model_name
    else:
        item = ET.SubElement(init, "Item")
        ET.SubElement(item, "modelName").text = model_name
        ET.SubElement(item, "txdName").text = model_name
        ET.SubElement(item, "ptfxAssetName").text = "NULL"
        lod = ET.SubElement(item, "lodDist")
        lod.set("value", "50")
        return
    init.append(item)


def merge_archetypes(base, src):
    for item in src.findall("./InitDatas/Item"):
        name = (item.findtext("modelName") or "").strip()
        if name:
            add_archetype(base, name)


def merge_animations(base, src):
    base_sets = base.find("WeaponAnimationsSets")
    src_sets = src.find("WeaponAnimationsSets")
    if src_sets is None:
        return
    if base_sets is None:
        base.append(copy.deepcopy(src_sets))
        return
    for src_set in src_sets.findall("Item"):
        key = src_set.get("key")
        src_anims = src_set.find("WeaponAnimations")
        entries = []
        if src_anims is not None:
            entries = [item for item in src_anims.findall("Item") if item.get("key")]
        base_set = None
        for item in base_sets.findall("Item"):
            if item.get("key") == key:
                base_set = item
                break
        if base_set is None:
            if entries:
                base_sets.append(copy.deepcopy(src_set))
            continue
        base_anims = base_set.find("WeaponAnimations")
        if base_anims is None:
            base_anims = ET.SubElement(base_set, "WeaponAnimations")
        have = {item.get("key") for item in base_anims.findall("Item")}
        for entry in entries:
            if entry.get("key") not in have:
                base_anims.append(copy.deepcopy(entry))
                have.add(entry.get("key"))


def _weapon_names(weapons_el):
    if weapons_el is None:
        return []
    return [(item.text or "").strip() for item in weapons_el.findall("Item") if (item.text or "").strip()]


def _add_weapon_names(weapons_el, names):
    have = set(_weapon_names(weapons_el))
    for name in names:
        if name not in have:
            node = ET.SubElement(weapons_el, "Item")
            node.text = name
            have.add(name)


def _clip_signature(group):
    parts = []
    for tag in ("Clip", "MovementClipSetId", "WeaponClipSetId", "UnholsterClipSetId", "UnholsterClipData"):
        for node in group.iter(tag):
            parts.append(f"{tag}={(node.text or '').strip()}")
    return "|".join(parts)


def merge_pedpersonality(base, src):
    _merge_unholster(base.find("MovementModeUnholsterData"), src.find("MovementModeUnholsterData"), base, src)
    _merge_movement_modes(base.find("MovementModes"), src.find("MovementModes"), base, src)


def _merge_unholster(base_el, src_el, base_root, src_root):
    if src_el is None:
        return
    if base_el is None:
        base_root.insert(0, copy.deepcopy(src_el))
        return
    for src_mode in src_el.findall("Item"):
        name = (src_mode.findtext("Name") or "").strip()
        base_mode = next((item for item in base_el.findall("Item") if (item.findtext("Name") or "").strip() == name), None)
        if base_mode is None:
            base_el.append(copy.deepcopy(src_mode))
            continue
        src_clips = src_mode.find("UnholsterClips")
        base_clips = base_mode.find("UnholsterClips")
        if src_clips is None:
            continue
        if base_clips is None:
            base_mode.append(copy.deepcopy(src_clips))
            continue
        for src_clip in src_clips.findall("Item"):
            sig = (src_clip.findtext("Clip") or "").strip()
            match = next((item for item in base_clips.findall("Item") if (item.findtext("Clip") or "").strip() == sig), None)
            if match is None:
                base_clips.append(copy.deepcopy(src_clip))
            else:
                _add_weapon_names(match.find("Weapons"), _weapon_names(src_clip.find("Weapons")))


def _merge_movement_modes(base_el, src_el, base_root, src_root):
    if src_el is None:
        return
    if base_el is None:
        base_root.append(copy.deepcopy(src_el))
        return
    for src_mode in src_el.findall("Item"):
        name = (src_mode.findtext("Name") or "").strip()
        base_mode = next((item for item in base_el.findall("Item") if (item.findtext("Name") or "").strip() == name), None)
        if base_mode is None:
            base_el.append(copy.deepcopy(src_mode))
            continue
        src_inner = src_mode.find("MovementModes")
        base_inner = base_mode.find("MovementModes")
        if src_inner is None:
            continue
        if base_inner is None:
            base_mode.append(copy.deepcopy(src_inner))
            continue
        for src_wrap in src_inner.findall("Item"):
            src_group = src_wrap.find("Item")
            if src_group is None:
                continue
            sig = _clip_signature(src_group)
            match = None
            for base_wrap in base_inner.findall("Item"):
                base_group = base_wrap.find("Item")
                if base_group is not None and _clip_signature(base_group) == sig:
                    match = base_group
                    break
            if match is None:
                base_inner.append(copy.deepcopy(src_wrap))
            else:
                _add_weapon_names(match.find("Weapons"), _weapon_names(src_group.find("Weapons")))


def _slot_rows(group):
    slots = group.find("WeaponSlots")
    if slots is None:
        return []
    return slots.findall("Item")


def merge_weapon_meta(base, src):
    _merge_navigate(base, src)
    _merge_best(base, src)
    _merge_infos(base, src)


def _merge_navigate(base, src):
    src_nav = src.find("SlotNavigateOrder")
    if src_nav is None:
        return
    base_nav = base.find("SlotNavigateOrder")
    if base_nav is None:
        base.insert(0, copy.deepcopy(src_nav))
        return
    base_groups = base_nav.findall("Item")
    src_groups = src_nav.findall("Item")
    if len(src_groups) == 1 and len(base_groups) > 1:
        targets = base_groups
        groups = src_groups
        for base_group in targets:
            slots = base_group.find("WeaponSlots")
            for row in _slot_rows(groups[0]):
                slots.append(copy.deepcopy(row))
        return
    for index, src_group in enumerate(src_groups):
        if index < len(base_groups):
            slots = base_groups[index].find("WeaponSlots")
            for row in _slot_rows(src_group):
                slots.append(copy.deepcopy(row))
        else:
            base_nav.append(copy.deepcopy(src_group))


def _merge_best(base, src):
    src_best = src.find("SlotBestOrder")
    if src_best is None:
        return
    base_best = base.find("SlotBestOrder")
    if base_best is None:
        nav = base.find("SlotNavigateOrder")
        index = list(base).index(nav) + 1 if nav is not None else 0
        base.insert(index, copy.deepcopy(src_best))
        return
    base_slots = base_best.find("WeaponSlots")
    for row in _slot_rows(src_best):
        base_slots.append(copy.deepcopy(row))


def _info_kind(item):
    info_type = item.get("type") or ""
    if info_type == "CWeaponInfo" or info_type.startswith("CWeapon"):
        return "weapon"
    if info_type.startswith("CAmmo"):
        return "ammo"
    return "other"


def _merge_infos(base, src):
    src_infos = src.find("Infos")
    if src_infos is None:
        return
    base_infos = base.find("Infos")
    if base_infos is None:
        base.append(copy.deepcopy(src_infos))
        return
    base_blocks = base.findall("./Infos/Item/Infos")

    def block_for(kind):
        for block in base_blocks:
            if any(_info_kind(item) == kind for item in block.findall("Item")):
                return block
        if kind == "weapon" and base_blocks:
            return base_blocks[-1]
        if base_blocks:
            return base_blocks[0]
        wrapper = ET.SubElement(base_infos, "Item")
        block = ET.SubElement(wrapper, "Infos")
        base_blocks.append(block)
        return block

    for src_block in src.findall("./Infos/Item/Infos"):
        for item in src_block.findall("Item"):
            name = (item.findtext("Name") or "").strip()
            dest = block_for(_info_kind(item))
            if name and any((have.findtext("Name") or "").strip() == name for have in dest.findall("Item")):
                continue
            dest.append(copy.deepcopy(item))


def publish(staging, dest):
    backup = None
    if dest.exists():
        backup = dest.with_name(dest.name + ".replacing")
        if backup.exists():
            shutil.rmtree(backup)
        dest.rename(backup)
    try:
        shutil.move(str(staging), str(dest))
    except Exception:
        if backup is not None and backup.exists() and not dest.exists():
            backup.rename(dest)
        raise
    if backup is not None and backup.exists():
        shutil.rmtree(backup)


def _prepare(weapons, templates_dir, models_dir):
    seen = set()
    prepared = []
    for template_name, ingame, model_name in weapons:
        ingame = ingame.strip().upper()
        if not NAME_RE.fullmatch(ingame):
            raise GenerateError(f"ชื่อในเกมใช้ได้แค่ A-Z, 0-9 และ _: {ingame}")
        if ingame in seen:
            raise GenerateError(f"ชื่อในเกมซ้ำในชุดเดียวกัน: {ingame}")
        seen.add(ingame)
        template_dir = find_template(templates_dir, template_name)
        model_dir, model_stem = resolve_model(models_dir, model_name)
        prepared.append((template_dir, ingame, model_dir, model_stem))
    if not prepared:
        raise GenerateError("ไม่มีอาวุธให้สร้าง")
    return prepared


def _write_texts(meta_dir, texts):
    meta_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in texts.items():
        (meta_dir / filename).write_text(text, encoding="utf-8", newline="\n")


def _check_resource_name(name):
    if not RESOURCE_RE.fullmatch(name or ""):
        raise GenerateError(f"ชื่อ resource ใช้ได้แค่ตัวอักษร ตัวเลข และ _: {name}")


def generate(mode, resource_name, weapons, templates_dir=TEMPLATES, models_dir=MODELS, output_dir=OUTPUT):
    mode = mode.lower()
    if mode not in ("separate", "pack"):
        raise GenerateError("โหมดต้องเป็น separate หรือ pack")
    prepared = _prepare(weapons, templates_dir, models_dir)
    if mode == "separate" and len(prepared) != 1:
        raise GenerateError("โหมดแยกสคริปต์รับทีละหนึ่งอาวุธ")
    if mode == "pack":
        _check_resource_name(resource_name)

    orders, next_order = take_orders(output_dir, len(prepared))
    filled = []
    for (template_dir, ingame, model_dir, model_stem), order in zip(prepared, orders):
        texts = fill_weapon(template_dir, ingame, model_stem, order)
        filled.append((ingame, model_dir, model_stem, texts))

    staging = Path(tempfile.mkdtemp(prefix="wpmod-"))
    written = []
    try:
        if mode == "separate":
            ingame, model_dir, model_stem, texts = filled[0]
            resource = staging / ingame
            _write_separate(resource, texts, model_dir, model_stem)
            written.append(output_dir / ingame)
            publish(resource, output_dir / ingame)
        else:
            resource = staging / resource_name
            _write_pack(resource, filled)
            written.append(output_dir / resource_name)
            publish(resource, output_dir / resource_name)
        commit_order(output_dir, next_order)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return written


def _write_separate(resource, texts, model_dir, model_stem):
    meta_dir = resource / "meta"
    stems = copy_stream(model_dir, resource / "stream")
    extras = [stem for stem in stems if stem.lower() != model_stem.lower()]
    if extras and "weaponarchetypes.meta" in texts:
        root = ET.fromstring(texts["weaponarchetypes.meta"])
        for stem in extras:
            add_archetype(root, stem)
        write_xml(meta_dir / "weaponarchetypes.meta", root)
        texts = {key: value for key, value in texts.items() if key != "weaponarchetypes.meta"}
    _write_texts(meta_dir, texts)
    write_manifest(resource, set(texts) | ({"weaponarchetypes.meta"} if extras else set()))


def _write_pack(resource, filled):
    merged = {filename: ET.fromstring(text) for filename, text in filled[0][3].items()}
    extra_models = []
    stream_dir = resource / "stream"
    for ingame, model_dir, model_stem, texts in filled:
        stems = copy_stream(model_dir, stream_dir)
        extra_models.extend(stem for stem in stems if stem.lower() != model_stem.lower())
    for _ingame, _model_dir, _model_stem, texts in filled[1:]:
        for filename, text in texts.items():
            src = ET.fromstring(text)
            if filename not in merged:
                merged[filename] = src
                continue
            if filename == "weaponarchetypes.meta":
                merge_archetypes(merged[filename], src)
            elif filename == "weaponanimations.meta":
                merge_animations(merged[filename], src)
            elif filename == "pedpersonality.meta":
                merge_pedpersonality(merged[filename], src)
            elif filename == "weapon.meta":
                merge_weapon_meta(merged[filename], src)
            elif filename == "weaponcomponents.meta":
                for child in list(src):
                    merged[filename].append(copy.deepcopy(child))
    if "weaponarchetypes.meta" in merged:
        for stem in extra_models:
            add_archetype(merged["weaponarchetypes.meta"], stem)
    meta_dir = resource / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    for filename, root in merged.items():
        write_xml(meta_dir / filename, root)
    write_manifest(resource, set(merged))


def _ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _pick(title, options):
    print(title)
    for index, name in enumerate(options, 1):
        print(f"  {index}  {name}")
    raw = _ask("เลือกเลขหรือพิมพ์ชื่อ: ")
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw


def _ask_weapon_name():
    raw = _ask("ชื่อในเกม (เช่น WEAPON_BASEBALL_DX): ").upper()
    if not NAME_RE.fullmatch(raw):
        raise GenerateError("ชื่อในเกมใช้ได้แค่ A-Z, 0-9 และ _")
    if not raw.startswith("WEAPON_"):
        answer = _ask(f"ใช้ชื่อ WEAPON_{raw} ? [Y/n]: ").lower()
        if answer in ("", "y", "yes"):
            raw = "WEAPON_" + raw
    return raw


def _ask_weapon(templates_dir, models_dir):
    template = _pick("template:", list_templates(templates_dir))
    ingame = _ask_weapon_name()
    model = _pick("โมเดลใน wp-models:", list_models(models_dir))
    if not template or not model:
        raise GenerateError("ต้องเลือก template และโมเดล")
    return template, ingame, model


def interactive(templates_dir=TEMPLATES, models_dir=MODELS, output_dir=OUTPUT):
    print("1  แยกสคริปต์  (หนึ่งอาวุธต่อหนึ่ง resource)")
    print("2  pack         (หลายอาวุธใน resource เดียว)")
    mode_raw = _ask("โหมด [1/2]: ")
    mode = {"1": "separate", "2": "pack", "separate": "separate", "pack": "pack"}.get(mode_raw.lower())
    if mode is None:
        raise GenerateError("เลือกโหมด 1 หรือ 2")
    if mode == "pack":
        resource_name = _ask("ชื่อโฟลเดอร์ resource: ")
        weapons = [_ask_weapon(templates_dir, models_dir)]
        while _ask("เพิ่มอาวุธอีกไหม [y/N]: ").lower() in ("y", "yes"):
            weapons.append(_ask_weapon(templates_dir, models_dir))
    else:
        template, ingame, model = _ask_weapon(templates_dir, models_dir)
        resource_name = ingame
        weapons = [(template, ingame, model)]
    written = generate(mode, resource_name, weapons, templates_dir, models_dir, output_dir)
    for path in written:
        print(f"สร้างแล้ว {path}")


def _print_usage():
    print(
        "\n".join(
            [
                "ใช้:",
                "  auto-complete.cmd",
                "  auto-complete.cmd separate TEMPLATE INGAME MODEL",
                "  auto-complete.cmd pack RESOURCE TEMPLATE INGAME MODEL [TEMPLATE INGAME MODEL ...]",
                "",
                "ตัวอย่าง:",
                "  auto-complete.cmd separate WEAPON_BAT WEAPON_BASEBALL_DX weapon_baseball_dx",
                "  auto-complete.cmd pack weapons_pack WEAPON_BAT WEAPON_BASEBALL_DX weapon_baseball_dx WEAPON_POOLCUE WEAPON_POOL_DX weapon_pool_dx",
            ]
        )
    )


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args:
            interactive()
            return 0
        if args[0] in ("-h", "--help"):
            _print_usage()
            return 0
        mode = args[0].lower()
        if mode == "separate":
            if len(args) != 4:
                _print_usage()
                return 1
            _template, ingame, _model = args[1:]
            written = generate(mode, ingame, [tuple(args[1:4])])
        elif mode == "pack":
            if len(args) < 5 or (len(args) - 2) % 3 != 0:
                _print_usage()
                return 1
            triplets = [tuple(args[index : index + 3]) for index in range(2, len(args), 3)]
            written = generate(mode, args[1], triplets)
        else:
            _print_usage()
            return 1
        for path in written:
            print(f"สร้างแล้ว {path}")
        return 0
    except GenerateError as error:
        print(f"ผิดพลาด: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
