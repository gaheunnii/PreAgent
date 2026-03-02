import os
import nbformat

def find_files(root, exts):
    result = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if any(f.endswith(ext) for ext in exts):
                result.append(os.path.join(dirpath, f))
    return result

def count_py_lines(py_files):
    py_total = 0
    py_file_lines = {}
    for f in py_files:
        with open(f, 'r', encoding='utf-8') as fp:
            lines = [line for line in fp if line.strip() and not line.strip().startswith('#')]
            py_file_lines[f] = len(lines)
            py_total += len(lines)
    return py_file_lines, py_total

def count_ipynb_lines(ipynb_files):
    ipynb_total = 0
    ipynb_file_lines = {}
    for f in ipynb_files:
        with open(f, 'r', encoding='utf-8') as fp:
            nb = nbformat.read(fp, as_version=4)
            code_lines = 0
            for cell in nb.cells:
                if cell.cell_type == 'code':
                    code_lines += len([l for l in cell.source.split('\n') if l.strip()])
            ipynb_file_lines[f] = code_lines
            ipynb_total += code_lines
    return ipynb_file_lines, ipynb_total

if __name__ == '__main__':
    root = os.path.dirname(os.path.abspath(__file__))
    py_files = find_files(root, ['.py'])
    ipynb_files = find_files(root, ['.ipynb'])
    py_file_lines, py_total = count_py_lines(py_files)
    ipynb_file_lines, ipynb_total = count_ipynb_lines(ipynb_files)

    print('Python 文件代码行数:')
    for f, n in py_file_lines.items():
        print(f'{f}: {n}')
    print(f'合计: {py_total}')
    print('\nJupyter Notebook 代码行数:')
    for f, n in ipynb_file_lines.items():
        print(f'{f}: {n}')
    print(f'合计: {ipynb_total}')
    print(f'\n总代码行数: {py_total + ipynb_total}')
