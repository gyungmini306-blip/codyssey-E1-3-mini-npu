"""Python 3.8+, standard library only: Mini NPU Simulator."""
import argparse
import json
import math
import re
import shutil
import textwrap
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


def number_text(value):
    """Keep numeric values visible; omit .0 only for whole numbers."""
    return str(int(value)) if value == int(value) else str(value)


def show_matrices(matrices):
    """Align numeric matrices and split wide matrices into column ranges."""
    size = len(matrices[0][1])
    cell_width = max(len(number_text(value)) for _, matrix in matrices
                     for row in matrix for value in row)
    screen = max(20, shutil.get_terminal_size(fallback=(80, 24)).columns)
    panel_width = max(size * (cell_width + 1) - 1,
                      max(sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F')
                              else 1 for ch in title) for title, _ in matrices))
    panels = max(1, min(len(matrices), (screen + 4) // (panel_width + 4)))
    if panel_width > screen:
        columns = max(1, (screen + 1) // (cell_width + 1))
        for title, matrix in matrices:
            for start in range(0, size, columns):
                end = min(size, start + columns)
                print('{} ({}~{}열)'.format(title, start + 1, end))
                for row in matrix:
                    print(' '.join(number_text(v).rjust(cell_width) for v in row[start:end]))
                print()
        return
    for start in range(0, len(matrices), panels):
        group = matrices[start:start + panels]
        headings = []
        for title, _ in group:
            width = sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
                        for ch in title)
            headings.append(title + ' ' * (panel_width - width))
        print('    '.join(headings).rstrip())
        for i in range(size):
            rows = [' '.join(number_text(v).rjust(cell_width) for v in matrix[i])
                    for _, matrix in group]
            print('    '.join(row.ljust(panel_width) for row in rows).rstrip())
        print()


def show_patterns(pattern, a, b, name_a, name_b, score_a, score_b):
    """Show actual input values, weights and products used to form the score."""
    size = len(pattern)
    for name, kernel, score in ((name_a, a, score_a), (name_b, b, score_b)):
        print('\n[{}와 계산]'.format(name))
        products = [[pattern[i][j] * kernel[i][j] for j in range(size)]
                    for i in range(size)]
        show_matrices([('입력값', pattern), (name + ' 필터값', kernel),
                       ('같은 자리끼리 곱한 값', products)])
        terms = [number_text(v) for row in products for v in row if v != 0]
        expression = ' + '.join(terms) if terms else '0'
        screen = max(20, shutil.get_terminal_size(fallback=(80, 24)).columns)
        print('0이 아닌 곱을 순서대로 더하면 (0인 항 생략):')
        print(textwrap.fill(expression, width=screen, break_long_words=False,
                            break_on_hyphens=False))
        print('점수 = {!r}'.format(score))


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
            print('십자가(Cross) 점수: {!r} | 엑스(X) 점수: {!r}'.format(a, b))
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
        while True:
            while mode not in ('1', '2', '3', '4', 'q'):
                print('\n1. 직접 입력하기 (3x3)')
                print('2. JSON 예제 전체 보기')
                print('3. JSON 예제 한 개만 보기')
                print('4. 오류 처리 예제 보기')
                print('q. 종료')
                mode = input('선택: ').strip().lower()
                if mode not in ('1', '2', '3', '4', 'q'):
                    print('1~4 또는 q를 입력하세요.')
            if mode == 'q':
                break
            try:
                if mode == '1':
                    interactive(args.generated_filters)
                elif mode == '2':
                    analyze(args.data, args.case)
                elif mode == '3':
                    cases = ('size_5_1', 'size_5_2', 'size_13_1',
                             'size_13_2', 'size_25_1', 'size_25_2')
                    for index, key in enumerate(cases, 1):
                        print('{}. {}'.format(index, key))
                    print('번호를 선택하거나 JSON의 케이스 이름을 직접 입력하세요.')
                    selected = input('예제 선택: ').strip()
                    if selected in ('1', '2', '3', '4', '5', '6'):
                        selected = cases[int(selected) - 1]
                    analyze(args.data, selected)
                else:
                    print('첫 케이스의 열 개수를 틀리게 만든 오류 처리 예제입니다.')
                    analyze(Path(__file__).parent / 'examples' / 'size-error.json')
            except ValueError as error:
                print('연산 오류: {}'.format(error))
            action = input('\n결과 확인 후 Enter: 메뉴로 돌아가기 / q: 종료 > ').strip().lower()
            while action not in ('', 'q'):
                action = input('Enter로 메뉴에 돌아가거나 q로 종료하세요 > ').strip().lower()
            if action == 'q':
                break
            mode = None
            args.case = None
            args.generated_filters = False
        print('프로그램을 종료합니다.')
    except (EOFError, KeyboardInterrupt):
        print('\n입력이 종료되어 프로그램을 마칩니다.')


if __name__ == '__main__':
    main()
