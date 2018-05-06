いまさら振り返るDjango Migration(Migrationの内部動作からやっちゃった事例まで)
========================================================================

http://www.dzeta.jp/~junjis/code_reading/index.php?Django%E3%82%92%E8%AA%AD%E3%82%80

toc
-----------

* whoami
* マイグレーションの呼び出し
    - modelクラス
    - makemigrations
    - migrate
* 手動でのマイグレーションファイル
    - uniq列の変更とか
    - AppConfig.get_model
* やらかした事例
    - migrationが長すぎて死ぬ
    - PRでは通ったがその後を含めるとリリースで死んだ
    - Fake?

whoami
--------------

* 自己紹介まとめておく

マイグレーションの流れ
-----------------------

### model
models.Modelでmodels.Fileld
 
### makemigrations

そもそもコマンドクラスがどうなっているか
django.core.management.commands.makemigrations.Command#handle

```
        # Load the current graph state. Pass in None for the connection so
        # the loader doesn't try to resolve replaced migrations from DB.
        loader = MigrationLoader(None, ignore_no_migrations=True)
```

connection=Noneなので接続せずにグラフを生成している。`__init__`の中で`build_graph`が呼ばれる


```
    def build_graph(self):
:
        # Load disk data
        self.load_disk()  # -> ローカルのマイグレーションファイルを読み込んでいる
        # Load database data
        if self.connection is None:
            self.applied_migrations = set()
        else:
            recorder = MigrationRecorder(self.connection)
            self.applied_migrations = recorder.applied_migrations()
```


load_disk
```
{('admin', '0001_initial'): <Migration admin.0001_initial>,
 ('admin', '0002_logentry_remove_auto_add'): <Migration admin.0002_logentry_remove_auto_add>,
 ('auth', '0001_initial'): <Migration auth.0001_initial>,
 ('auth', '0002_alter_permission_name_max_length'): <Migration auth.0002_alter_permission_name_max_length>,
 ('auth', '0003_alter_user_email_max_length'): <Migration auth.0003_alter_user_email_max_length>,
 ('auth', '0004_alter_user_username_opts'): <Migration auth.0004_alter_user_username_opts>,
 ('auth', '0005_alter_user_last_login_null'): <Migration auth.0005_alter_user_last_login_null>,
 ('auth', '0006_require_contenttypes_0002'): <Migration auth.0006_require_contenttypes_0002>,
 ('auth', '0007_alter_validators_add_error_messages'): <Migration auth.0007_alter_validators_add_error_messages>,
 ('auth', '0008_alter_user_username_max_length'): <Migration auth.0008_alter_user_username_max_length>,
 ('auth', '0009_alter_user_last_name_max_length'): <Migration auth.0009_alter_user_last_name_max_length>,
 ('contenttypes', '0001_initial'): <Migration contenttypes.0001_initial>,
 ('contenttypes', '0002_remove_content_type_name'): <Migration contenttypes.0002_remove_content_type_name>,
 ('sessions', '0001_initial'): <Migration sessions.0001_initial>}
```


まずはマイグレーション同士でのツリーを構成する。ツリー構成中は一時的にDummyNodeを作成しており

```
        if child not in self.nodes:
            error_message = (
                "Migration %s dependencies reference nonexistent"
                " child node %r" % (migration, child)
            )
            self.add_dummy_node(child, migration, error_message)
        if parent not in self.nodes:
            error_message = (
                "Migration %s dnonexistent"
                " parent node %r" % (migration, parent)
            )
```


ここらへんのエラーはみたことがあるのでは？このDummyNodeが残らず処理されていることをチェックします。


```
        conflicts = loader.detect_conflicts()
:
        if conflicts and not self.merge:
            name_str = "; ".join(
                "%s in %s" % (", ".join(names), app)
                for app, names in conflicts.items()
            )
            raise CommandError(
                "Conflicting migrations detected; multiple leaf nodes in the "
                "migration graph: (%s).\nTo fix them run "
                "'python manage.py makemigrations --merge'" % name_str
            )
```

confilictチェックが発生する。mergeを指定していれば勝手にマージする


```
        # Set up autodetector
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            questioner,
        )
```

detectorがマイグレーションの元ファイルを探す,ProjectStateは

```
{('admin', 'logentry'): <ModelState: 'admin.LogEntry'>,
 ('app1', 'author'): <ModelState: 'app1.Author'>,
 ('app1', 'book'): <ModelState: 'app1.Book'>,
 ('auth', 'group'): <ModelState: 'auth.Group'>,
 ('auth', 'permission'): <ModelState: 'auth.Permission'>,
 ('auth', 'user'): <ModelState: 'auth.User'>,
 ('contenttypes', 'contenttype'): <ModelState: 'contenttypes.ContentType'>,
 ('sessions', 'session'): <ModelState: 'sessions.Session'>}
```
こんな感じ

loader.project_state() とProjectState.from_apps(apps)の差分を取る

django.db.migrations.state.ProjectState 
オーバライドされているのは

```
    def __eq__(self, other):
        return self.models == other.models and set(self.real_apps) == set(other.real_apps)

```



```
        # Detect changes
        changes = autodetector.changes(
            graph=loader.graph,
            trim_to_apps=app_labels or None,
            convert_apps=app_labels or None,
            migration_name=self.migration_name,
        )
```

これでMigratiuonファイルを組み立てる

django.db.migrations.autodetector.MigrationAutodetector#_detect_changes
```
        # Renames have to come first
        self.generate_renamed_models()

        # Prepare lists of fields and generate through model map
        self._prepare_field_lists()
        self._generate_through_model_map()

        # Generate non-rename model operations
        self.generate_deleted_models()
        self.generate_created_models()
        self.generate_deleted_proxies()
        self.generate_created_proxies()
        self.generate_altered_options()
        self.generate_altered_managers()

        # Create the altered indexes and store them in self.altered_indexes.
        # This avoids the same computation in generate_removed_indexes()
        # and generate_added_indexes().
        self.create_altered_indexes()
        # Generate index removal operations before field is removed
        self.generate_removed_indexes()
        # Generate field operations
        self.generate_renamed_fields()
        self.generate_removed_fields()
        self.generate_added_fields()
        self.generate_altered_fields()
        self.generate_altered_unique_together()
        self.generate_altered_index_together()
        self.generate_added_indexes()
        self.generate_altered_db_table()
        self.generate_altered_order_with_respect_to()
```

django.db.migrations.writer.MigrationWriter

でMigrationを元にマイグレーションファイルを作成する

### migrate

django.core.management.commands.migrate.Command#handle

