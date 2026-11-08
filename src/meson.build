resources = gnome.compile_resources(
  'owly-drop',
  'owly-drop.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

install_subdir(
  'owly_drop',
  install_dir: pkgdatadir,
  exclude_directories: ['__pycache__', 'backend' / '__pycache__'],
)

launcher_conf = configuration_data()
launcher_conf.set('PYTHON', python3.full_path())
launcher_conf.set('VERSION', meson.project_version())
launcher_conf.set('MODULE_DIR', pkgdatadir)
launcher_conf.set('RESOURCE_FILE', pkgdatadir / 'owly-drop.gresource')
launcher_conf.set('LOCALE_DIR', get_option('prefix') / get_option('localedir'))
launcher_conf.set('SCHEMA_DIR', '')

configure_file(
  input: 'owly-drop.in',
  output: 'owly-drop',
  configuration: launcher_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

# The same launcher, pointed at the source and build directories:
#   meson compile -C build run
uninstalled_conf = configuration_data()
uninstalled_conf.merge_from(launcher_conf)
uninstalled_conf.set('MODULE_DIR', meson.current_source_dir())
uninstalled_conf.set('RESOURCE_FILE', meson.current_build_dir() / 'owly-drop.gresource')
uninstalled_conf.set('LOCALE_DIR', meson.project_build_root() / 'po')
uninstalled_conf.set('SCHEMA_DIR', meson.project_build_root() / 'data')

uninstalled_launcher = configure_file(
  input: 'owly-drop.in',
  output: 'owly-drop-uninstalled',
  configuration: uninstalled_conf,
)

run_target(
  'run',
  command: [python3, uninstalled_launcher],
  depends: [resources, gschemas, translations],
)
