project(
  'owly-drop',
  version: '0.2.0',
  meson_version: '>= 1.0.0',
  license: 'MIT',
)

app_id = 'io.github.Simon_du06.OwlyDrop'
resource_prefix = '/io/github/Simon_du06/OwlyDrop'
pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

i18n = import('i18n')
gnome = import('gnome')
python = import('python')

python3 = python.find_installation('python3')

# Needed to build; found here so a missing one is named clearly.
# Debian/Ubuntu: gettext and libglib2.0-dev-bin. Fedora: gettext and glib2-devel.
find_program('msgfmt')
find_program('glib-compile-resources')

subdir('po')
subdir('data')
subdir('src')
subdir('tests')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
