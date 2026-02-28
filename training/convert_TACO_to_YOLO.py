import json
import os
import shutil
import random  # used to randomize train/val split

#Class mapping
CLASS_MAP = {
    # ── Bottles ──────────────────────────────
    'Bottle':                       'Bottle',
    'Bottle cap':                   'Bottle',
    'Broken glass':                 'Bottle',
    'Other plastic bottle':         'Bottle',
    'Clear plastic bottle':         'Bottle',
    'Glass bottle':                 'Bottle',
    'Plastic bottle cap':           'Bottle',
    'Metal bottle cap':             'Bottle',
    'Glass jar':                    'Bottle',
    'Plastic lid':                  'Bottle',
    'Metal lid':                    'Bottle',

    # ── Cans ─────────────────────────────────
    'Aluminium foil':               'Can',
    'Drink can':                    'Can',
    'Food Can':                     'Can',
    'Aerosol':                      'Can',
    'Pop tab':                      'Can',
    'Scrap metal':                  'Can',

    # ── Plastic ──────────────────────────────
    'Plastic bag & wrapper':        'Plastic',
    'Plastic container':            'Plastic',
    'Plastic gloves':               'Plastic',
    'Plastic glooves':              'Plastic',   # typo in dataset
    'Plastic utensils':             'Plastic',
    'Six pack rings':               'Plastic',
    'Blister pack':                 'Plastic',
    'Aluminium blister pack':       'Plastic',
    'Carded blister pack':          'Plastic',
    'Other plastic':                'Plastic',
    'Plastic film':                 'Plastic',
    'Garbage bag':                  'Plastic',
    'Other plastic wrapper':        'Plastic',
    'Single-use carrier bag':       'Plastic',
    'Polypropylene bag':            'Plastic',
    'Crisp packet':                 'Plastic',
    'Spread tub':                   'Plastic',
    'Tupperware':                   'Plastic',
    'Other plastic container':      'Plastic',
    'Plastic straw':                'Plastic',
    'Styrofoam piece':              'Plastic',

    # ── Paper ────────────────────────────────
    'Paper bag':                    'Paper',
    'Paper cup':                    'Paper',
    'Meal carton':                  'Paper',
    'Pizza box':                    'Paper',
    'Egg carton':                   'Paper',
    'Drink carton':                 'Paper',
    'Wrapping paper':               'Paper',
    'Magazine paper':               'Paper',
    'Newspaper':                    'Paper',
    'Toilet tube':                  'Paper',
    'Other carton':                 'Paper',
    'Corrugated carton':            'Paper',
    'Tissues':                      'Paper',
    'Normal paper':                 'Paper',
    'Plastified paper bag':         'Paper',
    'Paper straw':                  'Paper',

    # ── Cups ─────────────────────────────────
    'Cup':                          'Cup',
    'Disposable food container':    'Cup',
    'Disposable plastic cup':       'Cup',
    'Foam cup':                     'Cup',
    'Glass cup':                    'Cup',
    'Other plastic cup':            'Cup',
    'Foam food container':          'Cup',

    # ── Cigarettes ───────────────────────────
    'Cigarette':                    'Cigarette',
    'Lighter':                      'Cigarette',

    # ── Food Waste ───────────────────────────
    'Food waste':                   'Food Waste',
    'Squeezable tube':              'Food Waste',

    # ── Unidentified ─────────────────────────
    'Battery':                      'Unidentified',
    'Rope & strings':               'Unidentified',
    'Shoe':                         'Unidentified',
    'Glove':                        'Unidentified',
    'Unlabeled litter':             'Unidentified',
}

FINAL_CLASSES = [
    'Bottle', 'Can', 'Plastic', 'Paper',
    'Cigarette', 'Food Waste', 'Cup', 'Unidentified'
]



# ── Main conversion function ──────────────────────────────────────
def convert_taco_to_yolo(annotations_path, images_dir, output_dir):
    
    with open(annotations_path, 'r') as f:
        data = json.load(f)

    # Create output folders
    for split in ['train', 'val']:
        os.makedirs(f'{output_dir}/images/{split}', exist_ok=True)
        os.makedirs(f'{output_dir}/labels/{split}', exist_ok=True)

    # Build lookups
    image_lookup = {img['id']: img for img in data['images']}

    annotations_by_image = {}
    for ann in data['annotations']:
        img_id = ann['image_id']
        if img_id not in annotations_by_image:
            annotations_by_image[img_id] = []
        annotations_by_image[img_id].append(ann)

    # Print what's in the dataset
    original_names = [cat['name'] for cat in data['categories']]
    print(f"Total images:      {len(data['images'])}")
    print(f"Total annotations: {len(data['annotations'])}")
    print(f"Original classes:  {len(original_names)}")
    print(f"Mapped to classes: {FINAL_CLASSES}")

    # 80/20 train/val split (randomized so batches aren’t grouped)
    all_ids = list(image_lookup.keys())
    random.shuffle(all_ids)
    split_idx = int(len(all_ids) * 0.8)
    train_ids = set(all_ids[:split_idx])

    converted = 0
    skipped = 0
    no_labels = 0

    for img_id, img_info in image_lookup.items():
        split = 'train' if img_id in train_ids else 'val'

        # ── Find the image file ──
        # TACO stores images as "batch_1/000001.jpg" etc.
        src_image = os.path.join(images_dir, img_info['file_name'])

        if not os.path.exists(src_image):
            print(f"  Missing: {src_image}")
            skipped += 1
            continue

        # Flatten batch_X/filename.jpg → batch_X_filename.jpg
        flat_name = img_info['file_name'].replace('/', '_').replace('\\', '_')
        dst_image = f"{output_dir}/images/{split}/{flat_name}"
        shutil.copy2(src_image, dst_image)

        # ── Write label file ──
        img_w = img_info['width']
        img_h = img_info['height']

        # Label file has same name as image but .txt
        label_name = os.path.splitext(flat_name)[0] + '.txt'
        label_file = f"{output_dir}/labels/{split}/{label_name}"

        annotations = annotations_by_image.get(img_id, [])
        lines = []

        for ann in annotations:
            # Get original class name
            cat_id = ann['category_id']
            original_name = next(
                (cat['name'] for cat in data['categories'] if cat['id'] == cat_id),
                None
            )

            if original_name is None:
                continue

            # Map to simplified class
            mapped = CLASS_MAP.get(original_name, None)
            if mapped is None:
                # Class not in our map at all - skip it
                continue

            cat_idx = FINAL_CLASSES.index(mapped)

            # COCO bbox: [x_min, y_min, width, height]
            x, y, w, h = ann['bbox']

            # YOLO bbox: [x_center, y_center, width, height] all normalized 0-1
            x_center = (x + w / 2) / img_w
            y_center = (y + h / 2) / img_h
            w_norm   = w / img_w
            h_norm   = h / img_h

            # Safety check - values must be between 0 and 1
            if not all(0 <= v <= 1 for v in [x_center, y_center, w_norm, h_norm]):
                continue

            lines.append(
                f"{cat_idx} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}"
            )

        # Write label file (even if empty - YOLOv8 expects it)
        with open(label_file, 'w') as f:
            f.write('\n'.join(lines))

        if not lines:
            no_labels += 1

        converted += 1

    # ── Write data.yaml ──
    yaml_content = f"""train: {os.path.abspath(output_dir)}/images/train
val:   {os.path.abspath(output_dir)}/images/val

nc: {len(FINAL_CLASSES)}
names: {FINAL_CLASSES}
"""
    with open(f'{output_dir}/data.yaml', 'w') as f:
        f.write(yaml_content)

    # ── Summary ──
    print(f"\n{'='*40}")
    print(f"Converted:        {converted} images")
    print(f"Skipped(missing): {skipped} images")
    print(f"No labels:        {no_labels} images")
    print(f"data.yaml:        {output_dir}/data.yaml")
    print(f"{'='*40}")
    print("Ready to train!")


# ── Run it ───────────────────────────────────────────────────────
convert_taco_to_yolo(
    annotations_path='TACO/data/annotations.json',   # NOT the unofficial one
    images_dir='TACO/data',
    output_dir='taco_yolo'
)