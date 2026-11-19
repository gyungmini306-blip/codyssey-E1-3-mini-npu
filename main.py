"""Python 3.8+, standard library only: Mini NPU Simulator."""
import argparse
import json
import math
import re
import shutil
import time
import unicodedata
from pathlib import Path

EPSILON = 1e-9
REPEATS = 1000
LABEL_NAMES = {'Cross': '십자가(Cross)', 'X': '엑스(X)',
               'UNDECIDED': '판정 불가(UNDECIDED)'}


def normalize_label(value):
    if not isinstance(value, str):
        raise ValueError('라벨은 문자열이어야 합니다.')
    labels = {'+': 'Cross', 'cross': 'Cross', 'x': 'X'}
    try:
        return labels[value.strip().lower()]
    except KeyError:
        raise ValueError('알 수 없는 라벨: {!r}'.format(value))


def validate_matrix(matrix, n):
    if not isinstance(matrix, list) or len(matrix) != n:
        raise ValueError('{}개 행이 필요합니다.'.format(n))
    result = []
    for row in matrix:
        if not isinstance(row, list) or len(row) != n:
            raise ValueError('각 행에는 {}개 숫자가 필요합니다.'.format(n))
        converted = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError('배열 원소는 숫자여야 합니다.')
            try:
                number = float(value)
            except (OverflowError, ValueError):
                raise ValueError('표현 가능한 유한한 숫자가 필요합니다.')
            if not math.isfinite(number):
                raise ValueError('NaN/무한대는 사용할 수 없습니다.')
            converted.append(number)
        result.append(converted)
    return result


def mac(pattern, kernel):
    total = 0.0
    for i in range(len(pattern)):
        for j in range(len(pattern)):
            total += pattern[i][j] * kernel[i][j]
    if not math.isfinite(total):
        raise ValueError('MAC 결과가 유한하지 않습니다(수치 범위 초과).')
    return total


def decide(a, b, label_a='Cross', label_b='X'):
    if abs(a - b) < EPSILON:
        return 'UNDECIDED'
    return label_a if a > b else label_b


def generate(n):
    """Return a center cross and both diagonals as n-by-n matrices."""
    cross = [[float(i == n // 2 or j == n // 2) for j in range(n)] for i in range(n)]
    x = [[float(i == j or i + j == n - 1) for j in range(n)] for i in range(n)]
    return cross, x


def show_patterns(pattern, a, b, name_a, name_b, score_a, score_b):
    """Show actual input/filter values and nonzero products using emoji cells."""
    binary = all(value in (0, 1) for matrix in (pattern, a, b)
                 for row in matrix for value in row)
    print('\n[그림: ⬜ 빈 칸(0), ⬛ 채운 칸(1)]')
    if not binary:
        print('실수 입력에서 ⬛는 0이 아닌 값이며, 겹친 칸에서는 곱이 0이 아닌 위치입니다.')
        print('점수는 원래 숫자로 계산하며 색칠된 칸 수와 다를 수 있습니다.')
    size = len(pattern)
    for name, kernel, score in ((name_a, a, score_a), (name_b, b, score_b)):
        print('\n{} 비교: {:g}점'.format(name, score))
        overlap = [[pattern[i][j] * kernel[i][j] for j in range(size)]
                   for i in range(size)]
        pictures = [('입력 그림', pattern, '⬛'), (name + ' 기준', kernel, '⬛'),
                    ('겹친 칸', overlap, '⬛')]
        width = max(size * 2, max(sum(2 if unicodedata.east_asian_width(ch)
                                    in ('W', 'F') else 1 for ch in title)
                                for title, _, _ in pictures))
        screen = shutil.get_terminal_size(fallback=(80, 24)).columns
        columns = max(1, min(3, (screen + 4) // (width + 4)))
        for start in range(0, len(pictures), columns):
            group = pictures[start:start + columns]
            headings = []
            for title, _, _ in group:
                text_width = sum(2 if unicodedata.east_asian_width(ch)
                                 in ('W', 'F') else 1 for ch in title)
                headings.append(title + ' ' * (width - text_width))
            print('    '.join(headings).rstrip())
            for i in range(size):
                rows = [''.join(filled if value != 0 else '⬜' for value in matrix[i])
                        + ' ' * (width - size * 2) for _, matrix, filled in group]
                print('    '.join(rows).rstrip())
            print()
        if binary:
            print('⬛ {:g}칸이 겹쳐서 {:g}점입니다.'.format(score, score))


def benchmark(samples):
    print('\n[성능 분석: MAC 1회 기준, 평균/{}회]'.format(REPEATS))
    print('크기       평균 시간(ms)    연산 횟수(N²)')
    for n in sorted(samples):
        pattern, kernel = samples[n]
        try:
            mac(pattern, kernel)  # warm-up, excluded from measurement
            start = time.perf_counter_ns()
            for _ in range(REPEATS):
                mac(pattern, kernel)
            average = (time.perf_counter_ns() - start) / REPEATS / 1_000_000
            print('{:2}x{:<2}      {:.6f}         {}'.format(n, n, average, n * n))
        except ValueError as error:
            print('{}x{} 측정 실패: {}'.format(n, n, error))


def read_matrix(title):
    print('\n{} (3줄, 각 줄에 숫자 3개)'.format(title))
    rows = []
    while len(rows) < 3:
        try:
            row = [float(item) for item in input('{}행: '.format(len(rows) + 1)).split()]
            if len(row) != 3 or not all(math.isfinite(v) for v in row):
                raise ValueError
        except ValueError:
            print('입력 형식 오류: 각 줄에 유한한 숫자 3개를 공백으로 구분해 입력하세요.')
            continue
        rows.append(row)
    return rows


def interactive(generated_filters=False):
    if generated_filters:
        a, b = generate(3)
        print('3x3 필터 자동 생성: A = 십자가(Cross), B = 엑스(X)')
    else:
        a = read_matrix('필터 A')
        b = read_matrix('필터 B')
    print('필터 A, B 저장 완료')
    pattern = read_matrix('패턴')
    start = time.perf_counter_ns()
    score_a, score_b = mac(pattern, a), mac(pattern, b)
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    show_patterns(pattern, a, b, '필터 A', '필터 B', score_a, score_b)
    print('\nA 점수: {:.16g}\nB 점수: {:.16g}'.format(score_a, score_b))
    print('두 필터 연산 시간: {:.6f} ms'.format(elapsed))
    result = decide(score_a, score_b, 'A', 'B')
    print('판정: {}'.format('판정 불가 (UNDECIDED)' if result == 'UNDECIDED' else result))
    benchmark({3: (pattern, a)})


def analyze(path, case_key=None):
    try:
        with open(path, encoding='utf-8-sig') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError('최상위 구조는 객체여야 합니다.')
        filters = data.get('filters')
        patterns = data.get('patterns')
        if not isinstance(patterns, dict):
            raise ValueError('patterns는 케이스 키를 가진 객체여야 합니다.')
    except (OSError, ValueError) as error:
        print('파일/스키마 오류: {}'.format(error))
        return

    if case_key is not None:
        if case_key not in patterns:
            print('선택한 케이스가 없습니다: {}'.format(case_key))
            return
        patterns = {case_key: patterns[case_key]}

    loaded, errors = {}, {}
    for n in (5, 13, 25):
        try:
            if not isinstance(filters, dict):
                raise ValueError('filters는 객체여야 합니다.')
            group = filters.get('size_{}'.format(n))
            if not isinstance(group, dict):
                raise ValueError('size_{} 필터 객체가 없습니다.'.format(n))
            normalized = {}
            for key, matrix in group.items():
                label = normalize_label(key)
                if label in normalized:
                    raise ValueError('정규화 후 필터 라벨 중복: ' + label)
                normalized[label] = validate_matrix(matrix, n)
            if set(normalized) != {'Cross', 'X'}:
                raise ValueError('Cross와 X 필터가 모두 필요합니다.')
            loaded[n] = normalized
            print('{}x{} 기준 필터 불러오기 완료: 십자가(Cross), 엑스(X)'.format(n, n))
        except ValueError as error:
            errors[n] = str(error)
            print('size_{} 필터 오류: {}'.format(n, error))

    failures = []
    for key, case in patterns.items():
        print('\n--- {} ---'.format(key))
        try:
            match = re.fullmatch(r'size_(5|13|25)_([0-9]+)', key)
            if not match:
                raise ValueError('패턴 키는 size_{5/13/25}_{idx} 형식이어야 합니다.')
            n = int(match.group(1))
            if n not in loaded:
                raise ValueError('필터 오류: ' + errors[n])
            if not isinstance(case, dict):
                raise ValueError('패턴 케이스는 객체여야 합니다.')
            pattern = validate_matrix(case.get('input'), n)
            expected = normalize_label(case.get('expected'))
            a = mac(pattern, loaded[n]['Cross'])
            b = mac(pattern, loaded[n]['X'])
            result = decide(a, b)
            passed = result == expected
            show_patterns(pattern, loaded[n]['Cross'], loaded[n]['X'],
                          '십자가', '엑스', a, b)
            print('십자가(Cross) 점수: {:.16g} | 엑스(X) 점수: {:.16g}'.format(a, b))
            print('판정: {} | 정답: {} | {}'.format(
                LABEL_NAMES[result], LABEL_NAMES[expected],
                '통과(PASS)' if passed else '실패(FAIL)'))
            if not passed:
                reason = '동점 규칙(|차이| < 1e-9)' if result == 'UNDECIDED' else '판정과 정답 불일치'
                failures.append((key, reason))
        except ValueError as error:
            print('실패(FAIL): {}'.format(error))
            failures.append((key, str(error)))

    # Generated valid inputs keep all required benchmark sizes available.
    benchmark({n: generate(n) for n in (3, 5, 13, 25)})
    print('\n[결과 요약]\n총 테스트: {} | 통과: {} | 실패: {}'.format(
        len(patterns), len(patterns) - len(failures), len(failures)))
    for key, reason in failures:
        print('- {}: {}'.format(key, reason))
    if not patterns:
        print('주의: 패턴이 없어 실제 검증된 케이스가 없습니다.')


def main():
    parser = argparse.ArgumentParser(description='Mini NPU Simulator')
    parser.add_argument('--mode', choices=('1', '2'))
    parser.add_argument('--case', help='JSON에서 한 케이스만 보기 (예: size_5_1)')
    parser.add_argument('--generated-filters', action='store_true',
                        help='3x3 십자가와 X 필터를 자동 생성해 모드 1을 실행합니다.')
    parser.add_argument('--data', type=Path, default=Path(__file__).with_name('data.json'))
    args = parser.parse_args()
    if args.mode == '2' and args.generated_filters:
        parser.error('--generated-filters는 모드 1에서 사용하세요.')
    if args.case and (args.mode == '1' or args.generated_filters):
        parser.error('--case는 JSON 분석 모드에서 사용하세요.')
    print('=== Mini NPU Simulator ===')
    try:
        mode = '2' if args.case else ('1' if args.generated_filters else args.mode)
        while mode not in ('1', '2'):
            print('1. 사용자 입력 (3x3)\n2. data.json 분석')
            mode = input('선택: ').strip()
            if mode not in ('1', '2'):
                print('1 또는 2를 입력하세요.')
        if mode == '1':
            interactive(args.generated_filters)
        else:
            analyze(args.data, args.case)
    except (EOFError, KeyboardInterrupt):
        print('\n입력이 종료되어 프로그램을 마칩니다.')
    except ValueError as error:
        print('연산 오류: {}'.format(error))


if __name__ == '__main__':
    main()
