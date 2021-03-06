import time
from collections import OrderedDict
from importlib import import_module

from django.apps import apps
from django.core.checks import Tags, run_checks
from django.core.management.base import BaseCommand, CommandError
from django.core.management.sql import (
    emit_post_migrate_signal, emit_pre_migrate_signal,
)
from django.db import DEFAULT_DB_ALIAS, connections, router
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import AmbiguityError
from django.db.migrations.state import ModelState, ProjectState
from django.utils.module_loading import module_has_submodule

from logging import getLogger
logger = getLogger('django_con')


class Command(BaseCommand):
    help = "Updates database schema. Manages both apps with migrations and those without."

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label', nargs='?',
            help='App label of an application to synchronize the state.',
        )
        parser.add_argument(
            'migration_name', nargs='?',
            help='Database state will be brought to the state after that '
                 'migration. Use the name "zero" to unapply all migrations.',
        )
        parser.add_argument(
            '--noinput', '--no-input', action='store_false', dest='interactive',
            help='Tells Django to NOT prompt the user for input of any kind.',
        )
        parser.add_argument(
            '--database', action='store', dest='database',
            default=DEFAULT_DB_ALIAS,
            help='Nominates a database to synchronize. Defaults to the "default" database.',
        )
        parser.add_argument(
            '--fake', action='store_true', dest='fake',
            help='Mark migrations as run without actually running them.',
        )
        parser.add_argument(
            '--fake-initial', action='store_true', dest='fake_initial',
            help='Detect if tables already exist and fake-apply initial migrations if so. Make sure '
                 'that the current database schema matches your initial migration before using this '
                 'flag. Django will only check for an existing table name.',
        )
        parser.add_argument(
            '--run-syncdb', action='store_true', dest='run_syncdb',
            help='Creates tables for apps without migrations.',
        )

    def _run_checks(self, **kwargs):
        issues = run_checks(tags=[Tags.database])
        issues.extend(super()._run_checks(**kwargs))
        return issues

    def handle(self, *args, **options):

        self.verbosity = options['verbosity']
        self.interactive = options['interactive']

        # @@ TODO あとで。
        # managementを読んで何をしているのか。
        # Import the 'management' module within each installed app, to register
        # dispatcher events.
        for app_config in apps.get_app_configs():
            if module_has_submodule(app_config.module, "management"):
                import_module('.management', app_config.name)

        logger.debug('options {}'.format(options))
        # @@ 普通は`default`が入っている
        db = options['database']
        # @@ 対応するDBへのコネクションラッパを取得する
        # ConnectionHandler().__getitem__(db)
        # django.db.backends.sqlite3.base.DatabaseWrapper が戻る
        connection = connections[db]
        logger.debug('connection {}'.format(connection))

        # @@ sqlite3では未実装なのでpass
        # 実際のところgisだけっぽい
        # postgisのbaseより。
        #     def prepare_database(self):
        #         super().prepare_database()
        #         # Check that postgis extension is installed.
        #         with self.cursor() as cursor:
        #             cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        connection.prepare_database()

        # Work out which apps have migrations and which do not
        # @@ executorの取得
        # migration_progress_callbackは進捗をstdoutにいい感じにだすための処理
        # DBから状態を取り出し、適用をするクラス
        executor = MigrationExecutor(connection, self.migration_progress_callback)

        # Raise an error if any migrations are applied before their dependencies.
        # @@
        # executor.loaderはMigrationLoader
        # 適用済マイグレーションのツリーの一貫性チェック
        # 適用されているマイグレーションのparentがgraph.nodesにあるかを見ている
        # どこかで辿りきれなくなっているのはまずいので。どこかで流れが変わっている可能性がある
        executor.loader.check_consistent_history(connection)

        # Before anything else, see if there's conflicting apps and drop out
        # hard if there are any
        # @@ マイグレーションファイルのコンフリクトチェック
        # 同じAppで複数のリーフが存在していないかを見ている
        conflicts = executor.loader.detect_conflicts()
        if conflicts:
            name_str = "; ".join(
                "%s in %s" % (", ".join(names), app)
                for app, names in conflicts.items()
            )
            raise CommandError(
                "Conflicting migrations detected; multiple leaf nodes in the "
                "migration graph: (%s).\nTo fix them run "
                "'python manage.py makemigrations --merge'" % name_str
            )

        # If they supplied command line arguments, work out what they mean.
        # @@ app_labelやmigration_nameの対応
        # 該当する部分だけをdisk_migrationから取り出す
        # 未指定なら全部の末端ノードを取り出す
        target_app_labels_only = True
        if options['app_label'] and options['migration_name']:
            app_label, migration_name = options['app_label'], options['migration_name']
            if app_label not in executor.loader.migrated_apps:
                raise CommandError(
                    "App '%s' does not have migrations." % app_label
                )
            if migration_name == "zero":
                targets = [(app_label, None)]
            else:
                try:
                    # @@
                    # migration_nameは前方一致で単一になればなんでもいい
                    migration = executor.loader.get_migration_by_prefix(app_label, migration_name)
                except AmbiguityError:
                    raise CommandError(
                        "More than one migration matches '%s' in app '%s'. "
                        "Please be more specific." %
                        (migration_name, app_label)
                    )
                except KeyError:
                    raise CommandError("Cannot find a migration matching '%s' from app '%s'." % (
                        migration_name, app_label))
                targets = [(app_label, migration.name)]
            target_app_labels_only = False
        elif options['app_label']:
            app_label = options['app_label']
            if app_label not in executor.loader.migrated_apps:
                raise CommandError(
                    "App '%s' does not have migrations." % app_label
                )
            targets = [key for key in executor.loader.graph.leaf_nodes() if key[0] == app_label]
        else:
            targets = executor.loader.graph.leaf_nodes()

        logger.debug('migration target {}'.format(targets))
        # @@
        # 実際に適用すべきマイグレーションを決定する
        plan = executor.migration_plan(targets)
        logger.debug('plan {}'.format(plan))
        # @@
        # https://docs.djangoproject.com/en/2.0/ref/django-admin/#django-admin-migrate
        # --run-syncdb¶
        # Allows creating tables for apps without migrations. While this isn’t recommended,
        # the migrations framework is sometimes too slow on large projects with hundreds of models.
        # これのためにあるらしい
        run_syncdb = options['run_syncdb'] and executor.loader.unmigrated_apps
        logger.debug('executor.loader.unmigrated_apps {}'.format(executor.loader.unmigrated_apps))

        # Print some useful info
        if self.verbosity >= 1:
            self.stdout.write(self.style.MIGRATE_HEADING("Operations to perform:"))
            if run_syncdb:
                self.stdout.write(
                    self.style.MIGRATE_LABEL("  Synchronize unmigrated apps: ") +
                    (", ".join(sorted(executor.loader.unmigrated_apps)))
                )
            if target_app_labels_only:
                self.stdout.write(
                    self.style.MIGRATE_LABEL("  Apply all migrations: ") +
                    (", ".join(sorted({a for a, n in targets})) or "(none)")
                )
            else:
                if targets[0][1] is None:
                    self.stdout.write(self.style.MIGRATE_LABEL(
                        "  Unapply all migrations: ") + "%s" % (targets[0][0],)
                    )
                else:
                    self.stdout.write(self.style.MIGRATE_LABEL(
                        "  Target specific migration: ") + "%s, from %s"
                        % (targets[0][1], targets[0][0])
                    )

        # @@ マイグレーション前のProjectStateを構成する
        # 恐らく適用済の範囲だけっぽい
        pre_migrate_state = executor._create_project_state(with_applied_migrations=True)
        pre_migrate_apps = pre_migrate_state.apps
        # @@ シグナルを投げる
        # 最終的にinject_rename_contenttypes_operationsが呼ばれる
        emit_pre_migrate_signal(
            self.verbosity, self.interactive, connection.alias, apps=pre_migrate_apps, plan=plan,
        )

        # Run the syncdb phase.
        if run_syncdb:
            if self.verbosity >= 1:
                self.stdout.write(self.style.MIGRATE_HEADING("Synchronizing apps without migrations:"))
            self.sync_apps(connection, executor.loader.unmigrated_apps)

        # Migrate!
        if self.verbosity >= 1:
            self.stdout.write(self.style.MIGRATE_HEADING("Running migrations:"))
        # @@ 適用するものがなければメッセージ出すだけ
        if not plan:
            if self.verbosity >= 1:
                self.stdout.write("  No migrations to apply.")
                # If there's changes that aren't in migrations yet, tell them how to fix it.
                # @@ これは優しさ
                # もしmakemigrationsされてない変更があれば警告する
                autodetector = MigrationAutodetector(
                    executor.loader.project_state(),
                    ProjectState.from_apps(apps),
                )
                changes = autodetector.changes(graph=executor.loader.graph)
                if changes:
                    self.stdout.write(self.style.NOTICE(
                        "  Your models have changes that are not yet reflected "
                        "in a migration, and so won't be applied."
                    ))
                    self.stdout.write(self.style.NOTICE(
                        "  Run 'manage.py makemigrations' to make new "
                        "migrations, and then re-run 'manage.py migrate' to "
                        "apply them."
                    ))
            fake = False
            fake_initial = False
        else:
            fake = options['fake']
            fake_initial = options['fake_initial']
        # @@ migrateを実行する
        post_migrate_state = executor.migrate(
            targets, plan=plan, state=pre_migrate_state.clone(), fake=fake,
            fake_initial=fake_initial,
        )
        # post_migrate signals have access to all models. Ensure that all models
        # are reloaded in case any are delayed.
        post_migrate_state.clear_delayed_apps_cache()
        post_migrate_apps = post_migrate_state.apps

        # Re-render models of real apps to include relationships now that
        # we've got a final state. This wouldn't be necessary if real apps
        # models were rendered with relationships in the first place.
        with post_migrate_apps.bulk_update():
            model_keys = []
            for model_state in post_migrate_apps.real_models:
                model_key = model_state.app_label, model_state.name_lower
                model_keys.append(model_key)
                post_migrate_apps.unregister_model(*model_key)
        post_migrate_apps.render_multiple([
            ModelState.from_model(apps.get_model(*model)) for model in model_keys
        ])

        # Send the post_migrate signal, so individual apps can do whatever they need
        # to do at this point.
        emit_post_migrate_signal(
            self.verbosity, self.interactive, connection.alias, apps=post_migrate_apps, plan=plan,
        )

    def migration_progress_callback(self, action, migration=None, fake=False):
        if self.verbosity >= 1:
            compute_time = self.verbosity > 1
            if action == "apply_start":
                if compute_time:
                    self.start = time.time()
                self.stdout.write("  Applying %s..." % migration, ending="")
                self.stdout.flush()
            elif action == "apply_success":
                elapsed = " (%.3fs)" % (time.time() - self.start) if compute_time else ""
                if fake:
                    self.stdout.write(self.style.SUCCESS(" FAKED" + elapsed))
                else:
                    self.stdout.write(self.style.SUCCESS(" OK" + elapsed))
            elif action == "unapply_start":
                if compute_time:
                    self.start = time.time()
                self.stdout.write("  Unapplying %s..." % migration, ending="")
                self.stdout.flush()
            elif action == "unapply_success":
                elapsed = " (%.3fs)" % (time.time() - self.start) if compute_time else ""
                if fake:
                    self.stdout.write(self.style.SUCCESS(" FAKED" + elapsed))
                else:
                    self.stdout.write(self.style.SUCCESS(" OK" + elapsed))
            elif action == "render_start":
                if compute_time:
                    self.start = time.time()
                self.stdout.write("  Rendering model states...", ending="")
                self.stdout.flush()
            elif action == "render_success":
                elapsed = " (%.3fs)" % (time.time() - self.start) if compute_time else ""
                self.stdout.write(self.style.SUCCESS(" DONE" + elapsed))

    def sync_apps(self, connection, app_labels):
        """Run the old syncdb-style operation on a list of app_labels."""
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)

        # Build the manifest of apps and models that are to be synchronized.
        all_models = [
            (
                app_config.label,
                router.get_migratable_models(app_config, connection.alias, include_auto_created=False),
            )
            for app_config in apps.get_app_configs()
            if app_config.models_module is not None and app_config.label in app_labels
        ]

        def model_installed(model):
            opts = model._meta
            converter = connection.introspection.table_name_converter
            return not (
                (converter(opts.db_table) in tables) or
                (opts.auto_created and converter(opts.auto_created._meta.db_table) in tables)
            )

        manifest = OrderedDict(
            (app_name, list(filter(model_installed, model_list)))
            for app_name, model_list in all_models
        )

        # Create the tables for each model
        if self.verbosity >= 1:
            self.stdout.write("  Creating tables...\n")
        with connection.schema_editor() as editor:
            for app_name, model_list in manifest.items():
                for model in model_list:
                    # Never install unmanaged models, etc.
                    if not model._meta.can_migrate(connection):
                        continue
                    if self.verbosity >= 3:
                        self.stdout.write(
                            "    Processing %s.%s model\n" % (app_name, model._meta.object_name)
                        )
                    if self.verbosity >= 1:
                        self.stdout.write("    Creating table %s\n" % model._meta.db_table)
                    editor.create_model(model)

            # Deferred SQL is executed when exiting the editor's context.
            if self.verbosity >= 1:
                self.stdout.write("    Running deferred SQL...\n")
