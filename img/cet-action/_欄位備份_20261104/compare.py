"""比對換圖前後的欄位備份。
用法：python compare.py <換圖前資料夾> <換圖後資料夾>
預期會變的只有「地球公民的行動」各 row 的圖片（fids / 檔名）；其他任何差異都會列為「非預期變動」。"""
import json, sys, glob, os

EXPECTED_ROW_KEYS = {'[field_comp_image][0][fids]'}
IGNORE_TOP = {'captured_at', 'url', 'page_title'}


def flat(d, prefix=''):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f'{prefix}/{k}'))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flat(v, f'{prefix}[{i}]'))
    else:
        out[prefix] = d
    return out


def main(before_dir, after_dir):
    unexpected = 0
    for bf in sorted(glob.glob(os.path.join(before_dir, '[0-9]*.json'))):
        tid = os.path.basename(bf)[:-5]
        af = os.path.join(after_dir, f'{tid}.json')
        if not os.path.exists(af):
            print(f'[{tid}] 換圖後沒有備份檔'); continue
        b = {k: v for k, v in json.load(open(bf, encoding='utf-8')).items() if k not in IGNORE_TOP}
        a = {k: v for k, v in json.load(open(af, encoding='utf-8')).items() if k not in IGNORE_TOP}
        fb, fa = flat(b), flat(a)
        for key in sorted(set(fb) | set(fa)):
            if fb.get(key) == fa.get(key):
                continue
            is_img = key.startswith('/ief/field_action_item[') and (
                any(key.endswith(e) for e in EXPECTED_ROW_KEYS) or '/files[' in key)
            tag = '預期（圖片）' if is_img else '非預期變動'
            if not is_img:
                unexpected += 1
            print(f'[{tid}] {tag}: {key}\n    前: {str(fb.get(key))[:200]}\n    後: {str(fa.get(key))[:200]}')
    print(f'\n非預期變動共 {unexpected} 項')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
