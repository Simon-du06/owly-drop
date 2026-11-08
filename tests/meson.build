pytest = find_program('pytest', 'pytest-3', required: false)
if pytest.found()
  test(
    'pytest',
    pytest,
    args: ['-q', meson.current_source_dir()],
    workdir: meson.project_source_root(),
    timeout: 120,
    suite: 'python',
  )
endif

msgfmt = find_program('msgfmt', required: false)
if msgfmt.found()
  fs = import('fs')
  foreach lang : fs.read(meson.project_source_root() / 'po' / 'LINGUAS').split()
    test(
      'check ' + lang + '.po',
      msgfmt,
      args: ['--check', '--output-file=/dev/null', meson.project_source_root() / 'po' / lang + '.po'],
      suite: 'po',
    )
  endforeach
endif
