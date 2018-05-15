いまさら振り返るDjango Migration(Migrationの内部動作からやっちゃった事例まで)
========================================================================

toc
-----------

* アイスブレイク
* 今日話すこと
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

アイスブレイク
--------------

### whoami

* 自己紹介まとめておく


### 弊社とPython

* Django
* Scrapy
* numpy, pandas, sklearn, TensorFlow

### 弊社とDjango

* Django 1.11
* Dango celery
* Django で DDD チックなことしてる(ドメインごとにModuleきるときれい)
* Django Channels 2.xの導入見込み
    - Channelsのチュートリアルはまじで面白いので読んでほしい
* daphne


今日話すこと
---------------

* マイグレーションを一緒に読んでみましょう
* 手でマイグレーションファイルを書くケースを見ましょう
* マイグレーションでやらかした話をお伝えし皆様にやらかさないようにしていただくために。

マイグレーションの流れ
-----------------------

### model
models.Modelでmodels.Fileld


### Djangoのコマンド

各モジュールの`management.commands`に作成したファイルでBaseCommandを継承したCommandクラスを作成して登録する。
実行時は`handle`メソッドが呼び出される

今回であれば以下の2つが該当する

* django.core.management.commands.makemigrations.Command#handle
* django.core.management.commands.migrate.Command#handle


### クラスなどの概略

* makemigrations.Command#handle
    * MigrationLoader: マイグレーションファイルからステートを構成する
        * MigrationGraph: ProjectStateを構成するためのグラフクラス
        * MigrationRecorder: django_migrationsとの中継、check_consistent_historyで使っている
    * ProjectState: プロジェクトのModelの状態を表現する
    * MigrationAutodetector: State間の差分を計算する
        - 全てのモデル名やField名をここで列挙する
    * makemigrations.Command#write_migration_files: マイグレーションファイルの書き出し
        - Migration(django.db.migrations.migration.Migration)を含んだDictから生成する
            * operations
        * MigrationWriter
            * OperationWriter: 各Operationに対応した文字列を生成する

* migrations.Command#handle
    * ConnectionHandler: DatabaseWrapperの管理
    * MigrationExecutor: DBから状態を取り出し、適用をするクラス
        * DatabaseWrapper: 各種DBとの接続、SQLの発行
            - schema_editorとMigrateで実際のマイグレーションをapplyする
                - 実際はOperationのApplyが呼び出される
        * MigrationLoader: マイグレーションファイルやローカルからマイグレーション情報を取得しStateを組み立てる
        * MigrationRecorder: django_migrationsとの中継,適用済マイグレーションの管理とかしている
    * MigrationAutodetector: makemigrationsされてない変更があれば警告する

MaigrationやOperationはmake時もmigrate時も利用されている。

### makemigrations
#### 流れ

1. app_labelsの指定があればそれの妥当性チェック
2. MigrationLoader で既存のマイグレーションファイルからProjectStateを構成
3. (唯一のDB接続) MigrationLoader.check_consistent_historyで一貫性チェック
4. リーフが集約しているかのチェック(detect_conflicts)
    - mergeを指定しない限りコンフリクト時はここで終了 
    - mergeを指定していればマージ処理をして終了
5. MigrationAutodetector で現在のAppのStateとマイグレーションファイルのStateの差分取得
6. 差分があればwrite_migration_filesでマイグレーションファイルの作成
7. MigrationWriterを通して各migrationをマイグレーションファイルとして書き出し

#### 詳細

django.core.management.commands.makemigrations.Command#handle


##### 1. app_labelsの指定があればそれの妥当性チェック


```python

from django.apps import apps
:
        # @@ makemigrationsに指定されたappがある場合はそれが存在するかのチェック
        app_labels = set(app_labels)
        bad_app_labels = set()
        for app_label in app_labels:
            try:
                apps.get_app_config(app_label)
            except LookupError:
                bad_app_labels.add(app_label)
        if bad_app_labels:
            for app_label in bad_app_labels:
                self.stderr.write("App '%s' could not be found. Is it in INSTALLED_APPS?" % app_label)
            sys.exit(2)
```

##### 2. MigrationLoader で既存のマイグレーションファイルからProjectStateを構成

```python
        # @@ マイグレーションファイルからステートを構成する
        # connection=NoneにしているのでDBは見ない
        # コンストラクタの中でbuild_graphが呼ばれる
        # ローカルのマイグレーションファイルを読み込んでグラフを構成する
        loader = MigrationLoader(None, ignore_no_migrations=True)
```

connection=Noneなので接続せずにグラフを生成している。`__init__`の中で`build_graph`が呼ばれる
makemigrationsの本質的な処理に於いてはDBは不要である。



```python
# django.db.migrations.loader.MigrationLoader#build_graph
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


load_diskの結果

```python
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


##### 3. (唯一のDB接続) MigrationLoader.check_consistent_historyで一貫性チェック

```python
                loader.check_consistent_history(connection)
```

```python
# django.db.migrations.loader.MigrationLoader#check_consistent_history
    def check_consistent_history(self, connection):
        """
        Raise InconsistentMigrationHistory if any applied migrations have
        unapplied dependencies.
        """
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        for migration in applied:
            # If the migration is unknown, skip it.
            if migration not in self.graph.nodes:
                continue
            for parent in self.graph.node_map[migration].parents:
                logger.debug('migration:{} parent:{} replacements:{}'.format(migration, parent, self.replacements))
                if parent not in applied:
                    # Skip unapplied squashed migrations that have all of their
                    # `replaces` applied.
                    # @@ ここはまぁ無視できる
                    if parent in self.replacements:
                        if all(m in applied for m in self.replacements[parent].replaces):
                            continue
                    raise InconsistentMigrationHistory(
                        "Migration {}.{} is applied before its dependency "
                        "{}.{} on database '{}'.".format(
                            migration[0], migration[1], parent[0], parent[1],
                            connection.alias,
                        )
                    )
```

適用済マイグレーションが見つかったらその全ての親が正しく適用されているかをチェックしている。

##### 4. リーフが集約しているかのチェック(detect_conflicts)

```python
        # Before anything else, see if there's conflicting apps and drop out
        # hard if there are any and they don't want to merge
        # @@ マイグレーションファイルのコンフリクトチェック
        # 同じAppで複数のリーフが存在していないかを見ている
        conflicts = loader.detect_conflicts()
:
:

        # @@ コンフリクトがあったときの通常対応
        # mergeを指定しない限り、同じAppでリーフが複数の場合はmergeの実行を促して終了する
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

        # If they want to merge and there's nothing to merge, then politely exit
        if self.merge and not conflicts:
            self.stdout.write("No conflicts detected to merge.")
            return

        # @@ merge action
        # --mergeを指定していればconflict解決のためのMergeを実行する
        if self.merge and conflicts:
            return self.handle_merge(loader, conflicts)
```

##### 5. MigrationAutodetector で現在のAppのStateとマイグレーションファイルのStateの差分取得


```python
        # @@ マイグレーション計算の肝であるDetectorを生成
        # loader.project_state -> Migrationファイルから計算したState
        # ProjectState.from_apps(apps) -> 現在のプロジェクトの状態から求めたState
        # MigrationAutodetectorは両者の差分を元にマイグレーションファイルを生成する機能をもつ
        # MigrationAutodetectorをここで初期化する
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            questioner,
        )
        logger.debug(autodetector)
:

        # @@ migrationの計算
        # {'app1': [<Migration app1.0002_book_author>]}
        changes = autodetector.changes(
            graph=loader.graph,
            trim_to_apps=app_labels or None,
            convert_apps=app_labels or None,
            migration_name=self.migration_name,
        )
```

```python
# django.db.migrations.autodetector.MigrationAutodetector#changes
    def changes(self, graph, trim_to_apps=None, convert_apps=None, migration_name=None):
        """
        Main entry point to produce a list of applicable changes.
        Take a graph to base names on and an optional set of apps
        to try and restrict to (restriction is not guaranteed)
        """
        logger.debug('changes {} {} {}'.format(trim_to_apps, convert_apps, migration_name))
        changes = self._detect_changes(convert_apps, graph)
        logger.debug(changes)
        # @@ マイグレーションファイル名の調整等
        changes = self.arrange_for_graph(changes, graph, migration_name)
        logger.debug(changes)
        # @@ app_labelが指定されている場合はそれ以外のChangeを捨てる
        if trim_to_apps:
            changes = self._trim_to_apps(changes, trim_to_apps)
        logger.debug(changes)
        return changes
```

```python
# django.db.migrations.autodetector.MigrationAutodetector#_detect_changes
    def _detect_changes(self, convert_apps=None, graph=None):
:
        self.generated_operations = {}
        self.altered_indexes = {}

        # Prepare some old/new state and model lists, separating
        # proxy models and ignoring unmigrated apps.
        self.old_apps = self.from_state.concrete_apps
        self.new_apps = self.to_state.apps
        self.old_model_keys = set()
        self.old_proxy_keys = set()
        self.old_unmanaged_keys = set()
        self.new_model_keys = set()
        self.new_proxy_keys = set()
        self.new_unmanaged_keys = set()
        # StateからモデルやFieldを取得してマスターデータを作る
        for al, mn in self.from_state.models:
            model = self.old_apps.get_model(al, mn)
            if not model._meta.managed:
                self.old_unmanaged_keys.add((al, mn))
            elif al not in self.from_state.real_apps:
                if model._meta.proxy:
                    self.old_proxy_keys.add((al, mn))
                else:
                    self.old_model_keys.add((al, mn))

        for al, mn in self.to_state.models:
            model = self.new_apps.get_model(al, mn)
            if not model._meta.managed:
                self.new_unmanaged_keys.add((al, mn))
            elif (
                al not in self.from_state.real_apps or
                (convert_apps and al in convert_apps)
            ):
                if model._meta.proxy:
                    self.new_proxy_keys.add((al, mn))
                else:
                    self.new_model_keys.add((al, mn))
```

```python

        # @@ マイグレーションの検知処理
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

        self._sort_migrations()
        self._build_migration_list(graph)
        self._optimize_migrations()

        return self.migrations
```

各変更点の捜索をそれぞれやる

```python
# django.db.migrations.autodetector.MigrationAutodetector#generate_added_fields
    def generate_added_fields(self):
        """Make AddField operations."""
        # @@ 既存のフィールドとの差分を取って列追加を検知する
        # ('app1', 'book', 'author') のような形式
        logger.debug('old_field_keys {}'.format(self.old_field_keys))
        logger.debug('new_filed_keys {}'.format(self.new_field_keys))
        logger.debug('diff  {}'.format(sorted(self.new_field_keys - self.old_field_keys)))
        for app_label, model_name, field_name in sorted(self.new_field_keys - self.old_field_keys):
            logger.debug('generate_added_fields {} {} {}'.format(app_label, model_name, field_name))
            self._generate_added_field(app_label, model_name, field_name)
```

差分はわりと豪快で、列のset同士を比較した差分を見る

```python
    def _generate_added_field(self, app_label, model_name, field_name):
        field = self.new_apps.get_model(app_label, model_name)._meta.get_field(field_name)
        # Fields that are foreignkeys/m2ms depend on stuff
        dependencies = []
        if field.remote_field and field.remote_field.model:
            dependencies.extend(self._get_dependencies_for_foreign_key(field))
        # You can't just add NOT NULL fields with no default or fields
        # which don't allow empty strings as default.
        time_fields = (models.DateField, models.DateTimeField, models.TimeField)
        preserve_default = (
            field.null or field.has_default() or field.many_to_many or
            (field.blank and field.empty_strings_allowed) or
            (isinstance(field, time_fields) and field.auto_now)
        )
        if not preserve_default:
            field = field.clone()
            if isinstance(field, time_fields) and field.auto_now_add:
                field.default = self.questioner.ask_auto_now_add_addition(field_name, model_name)
            else:
                field.default = self.questioner.ask_not_null_addition(field_name, model_name)
        self.add_operation(
            app_label,
            operations.AddField(
                model_name=model_name,
                name=field_name,
                field=field,
                preserve_default=preserve_default,
            ),
            dependencies=dependencies,
        )
```

生成されるchangesは`{'app1': [<Migration app1.0002_book_author>]}`みたいな形式

##### 6. 差分があればwrite_migration_filesでマイグレーションファイルの作成

```python
        if not changes:
            # No changes? Tell them.
            if self.verbosity >= 1:
                if app_labels:
                    if len(app_labels) == 1:
                        self.stdout.write("No changes detected in app '%s'" % app_labels.pop())
                    else:
                        self.stdout.write("No changes detected in apps '%s'" % ("', '".join(app_labels)))
                else:
                    self.stdout.write("No changes detected")
        else:
            # @@ マイグレーションファイルの作成
            self.write_migration_files(changes)
            if check_changes:
                sys.exit(1)
```

##### 7. MigrationWriterを通して各migrationをマイグレーションファイルとして書き出し

```python

    def write_migration_files(self, changes):
:
        # changes は {'app1': [<Migration app1.0002_book_author>]}
        for app_label, app_migrations in changes.items():
            # @@ app1 [<Migration app1.0002_book_author>]
            logger.debug('write_migration_files {} {}'.format(app_label, app_migrations))
            :
            for migration in app_migrations:
                # Describe the migration
                # @@ Migrationから書き出し用のMigrationWriterを取得する
                writer = MigrationWriter(migration)
                :
                if not self.dry_run:
                :
                    migration_string = writer.as_string()
                    # @@ 実際にマイグレーションファイルを書き出す
                    with open(writer.path, "w", encoding='utf-8') as fh:
                        fh.write(migration_string)
:
```

```python
# django.db.migrations.writer.MigrationWriter#as_string
    def as_string(self):
        """Return a string of the file contents."""
        items = {
            "replaces_str": "",
            "initial_str": "",
        }

        imports = set()

        # Deconstruct operations
        operations = []
        for operation in self.migration.operations:
            logger.debug('operation {}'.format(operation))
            # @@ Operation単位でコマンドに変換
            operation_string, operation_imports = OperationWriter(operation).serialize()
            logger.debug('operation_string, operation_imports {} {}'.format(operation_string, operation_imports))
            # @@ importsは一回やればいいからsetになっている
            imports.update(operation_imports)
            operations.append(operation_string)
```

```python

class OperationWriter:
    def __init__(self, operation, indentation=2):
        self.operation = operation
        self.buff = []
        self.indentation = indentation

    def serialize(self):

        def _write(_arg_name, _arg_value):
            if (_arg_name in self.operation.serialization_expand_args and
                    isinstance(_arg_value, (list, tuple, dict))):
                if isinstance(_arg_value, dict):
                    self.feed('%s={' % _arg_name)
                    self.indent()
                    for key, value in _arg_value.items():
                        key_string, key_imports = MigrationWriter.serialize(key)
                        arg_string, arg_imports = MigrationWriter.serialize(value)
                        args = arg_string.splitlines()
                        if len(args) > 1:
                            self.feed('%s: %s' % (key_string, args[0]))
                            for arg in args[1:-1]:
                                self.feed(arg)
                            self.feed('%s,' % args[-1])
                        else:
                            self.feed('%s: %s,' % (key_string, arg_string))
                        imports.update(key_imports)
                        imports.update(arg_imports)
                    self.unindent()
                    self.feed('},')
                else:
                    self.feed('%s=[' % _arg_name)
                    self.indent()
                    for item in _arg_value:
                        arg_string, arg_imports = MigrationWriter.serialize(item)
                        args = arg_string.splitlines()
                        if len(args) > 1:
                            for arg in args[:-1]:
                                self.feed(arg)
                            self.feed('%s,' % args[-1])
                        else:
                            self.feed('%s,' % arg_string)
                        imports.update(arg_imports)
                    self.unindent()
                    self.feed('],')
            else:
                arg_string, arg_imports = MigrationWriter.serialize(_arg_value)
                args = arg_string.splitlines()
                if len(args) > 1:
                    self.feed('%s=%s' % (_arg_name, args[0]))
                    for arg in args[1:-1]:
                        self.feed(arg)
                    self.feed('%s,' % args[-1])
                else:
                    self.feed('%s=%s,' % (_arg_name, arg_string))
                imports.update(arg_imports)

        imports = set()
        name, args, kwargs = self.operation.deconstruct()
        operation_args = get_func_args(self.operation.__init__)

        # See if this operation is in django.db.migrations. If it is,
        # We can just use the fact we already have that imported,
        # otherwise, we need to add an import for the operation class.
        if getattr(migrations, name, None) == self.operation.__class__:
            self.feed('migrations.%s(' % name)
        else:
            imports.add('import %s' % (self.operation.__class__.__module__))
            self.feed('%s.%s(' % (self.operation.__class__.__module__, name))

        self.indent()

        for i, arg in enumerate(args):
            arg_value = arg
            arg_name = operation_args[i]
            _write(arg_name, arg_value)

        i = len(args)
        # Only iterate over remaining arguments
        for arg_name in operation_args[i:]:
            if arg_name in kwargs:  # Don't sort to maintain signature order
                arg_value = kwargs[arg_name]
                _write(arg_name, arg_value)

        self.unindent()
        self.feed('),')
        return self.render(), imports
```

`django.db.migrations.operations.base.Operation`の`deconstruct`で必要な値が戻されている。

```python
class AddField(FieldOperation):
    """Add a field to a model."""

    def __init__(self, model_name, name, field, preserve_default=True):
        self.field = field
        self.preserve_default = preserve_default
        super().__init__(model_name, name)

    def deconstruct(self):
        kwargs = {
            'model_name': self.model_name,
            'name': self.name,
            'field': self.field,
        }
        if self.preserve_default is not True:
            kwargs['preserve_default'] = self.preserve_default
        return (
            self.__class__.__name__,
            [],
            kwargs
        )
```

### migrate
#### 流れ

1. `connection = connections[db]`でDBへの接続を取得
    - prepare_databaseは特に何もしてない
2. MigrationExecutorで整合性のチェックやファイル指定の判定
3. MigrationPlanの生成(migration fileのセットやbackwordの判定とか)
4. マイグレーション前のProjectStateを構成する
5. マイグレーションの実行
    - `self._migrate_all_forwards`
    - `apply_migration`
6. マイグレーションの実行(2)
    - SQLの発行
#### 詳細


##### 1. `connection = connections[db]`でDBへの接続を取得

```python
        # @@ 普通は`default`が入っている
        db = options['database']
        # @@ 対応するDBへのコネクションラッパを取得する
        # ConnectionHandler().__getitem__(db)
        # django.db.backends.sqlite3.base.DatabaseWrapper が戻る
        connection = connections[db]
```

```python
connections = ConnectionHandler()
```

```python
# django.db.utils.ConnectionHandler

class ConnectionHandler:
    def __init__(self, databases=None):
        """
        databases is an optional dictionary of database definitions (structured
        like settings.DATABASES).
        """
        self._databases = databases
        self._connections = local()
:
    def __getitem__(self, alias):
        if hasattr(self._connections, alias):
            return getattr(self._connections, alias)

        self.ensure_defaults(alias)
        self.prepare_test_settings(alias)
        db = self.databases[alias]
        # @@ DBに応じたドライバクラスをimportする
        # i.e. django.db.backends.sqlite3.base
        backend = load_backend(db['ENGINE'])
        conn = backend.DatabaseWrapper(db, alias)
        # @@
        # dbは設定のDict, aliasは設定名(default)
        logger.debug('conn, db, alias {} {} {}'.format(conn, db, alias))
        setattr(self._connections, alias, conn)
        return conn
```

`django.db.backends.base.base.BaseDatabaseWrapper`を実装するクラスのインスタンスが戻る。
SQLite3は`django.db.backends.sqlite3.base.DatabaseWrapper`

##### 2. MigrationExecutorで整合性のチェックやファイル指定の判定

```python
        # @@ executorの取得
        # migration_progress_callbackは進捗をstdoutにいい感じにだすための処理
        # DBから状態を取り出し、適用をするクラス
        executor = MigrationExecutor(connection, self.migration_progress_callback)
```

```python
# django.db.migrations.executor.MigrationExecutor

class MigrationExecutor:
    """
    End-to-end migration execution - load migrations and run them up or down
    to a specified set of targets.
    """

    def __init__(self, connection, progress_callback=None):
        self.connection = connection
        # @@ makemigrationでも使っているローダ
        # connectionを渡しているのでDBから読み込まれる
        # Stateを作るため.今回はDBのMigrateテーブルから取得している
        # Loaderの中でもRecorder使ってるけど
        self.loader = MigrationLoader(self.connection)
        # @@ Recorder
        # 適用済のMigrationをDBに永続化する
        # Migrationというモデルをもっていて、ORM経由でそこにしまっている
        self.recorder = MigrationRecorder(self.connection)
        # 進捗管理の関数
        self.progress_callback = progress_callback
```

MigrationLoaderやMigrationRecorderはここでも出てきている

```python
        # Raise an error if any migrations are applied before their dependencies.
        # @@
        # executor.loaderはMigrationLoader
        # 適用済マイグレーションのツリーの一貫性チェック
        # 適用されているマイグレーションのparentがgraph.nodesにあるかを見ている
        # どこかで辿りきれなくなっているのはまずいので。どこかで流れが変わっている可能性がある
        executor.loader.check_consistent_history(connection)

```



```python
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
```

makemigrationsでもしていた`check_consistent_history`や`detect_conflicts`を実行する


##### 3. MigrationPlanの生成(migration fileのセットやbackwordの判定とか)

```python
        # @@
        # 実際に適用すべきマイグレーションを決定する
        plan = executor.migration_plan(targets)
```

targetsは各Appのリーフノードが基本
`targets = [('admin', '0002_logentry_remove_auto_add'), ('app1', '0002_book_author'), ('auth', '0009_alter_user_last_name_max_length'), ('contenttypes', '0002_remove_content_type_name'), ('sessions', '0001_initial')]`


```python
# django.db.migrations.executor.MigrationExecutor#migration_plan
    def migration_plan(self, targets, clean_start=False):
        """
        Given a set of targets, return a list of (Migration instance, backwards?).
        """
        # @@
        # targets=[('admin', '0002_logentry_remove_auto_add'), ('app1', '0002_book_author'), ....]
        plan = []
        if clean_start:
            applied = set()
        else:
            applied = set(self.loader.applied_migrations)
        for target in targets:
:
            else:
                for migration in self.loader.graph.forwards_plan(target):
                    logger.debug('forwards_plan {} is applied {}'.format(migration, migration not in applied))
                    if migration not in applied:
                        plan.append((self.loader.graph.nodes[migration], False))
                        applied.add(migration)
```

```python
# django.db.migrations.graph.MigrationGraph#forwards_plan
    def forwards_plan(self, target):
        """
        Given a node, return a list of which previous nodes (dependencies) must
        be applied, ending with the node itself. This is the list you would
        follow if applying the migrations to a database.
        """
        if target not in self.nodes:
            raise NodeNotFoundError("Node %r not a valid node" % (target,), target)
        # Use parent.key instead of parent to speed up the frequent hashing in ensure_not_cyclic
        self.ensure_not_cyclic(target, lambda x: (parent.key for parent in self.node_map[x].parents))
        self.cached = True
        node = self.node_map[target]
        try:
            return node.ancestors()
        except RuntimeError:
            # fallback to iterative dfs
            warnings.warn(RECURSION_DEPTH_WARNING, RuntimeWarning)
            return self.iterative_dfs(node)
```


`plan = [(<Migration app1.0002_book_author>, False)]`


##### 4. マイグレーション前のProjectStateを構成する

```python
        # @@ マイグレーション前のProjectStateを構成する
        # 恐らく適用済の範囲だけっぽい
        pre_migrate_state = executor._create_project_state(with_applied_migrations=True)
        pre_migrate_apps = pre_migrate_state.apps
        # @@ シグナルを投げる
        # 最終的にinject_rename_contenttypes_operationsが呼ばれる
        emit_pre_migrate_signal(
            self.verbosity, self.interactive, connection.alias, apps=pre_migrate_apps, plan=plan,
        )
```

```python
# django/db/models/signals.py:52
pre_migrate = Signal(providing_args=["app_config", "verbosity", "interactive", "using", "apps", "plan"])
post_migrate = Signal(providing_args=["app_config", "verbosity", "interactive", "using", "apps", "plan"])

```

```python
# django.contrib.contenttypes.apps.ContentTypesConfig
class ContentTypesConfig(AppConfig):
    name = 'django.contrib.contenttypes'
    verbose_name = _("Content Types")

    def ready(self):
        pre_migrate.connect(inject_rename_contenttypes_operations, sender=self)
        post_migrate.connect(create_contenttypes)
        checks.register(check_generic_foreign_keys, checks.Tags.models)
        checks.register(check_model_name_lengths, checks.Tags.models)
```

```python
# django.contrib.contenttypes.management.inject_rename_contenttypes_operations
def inject_rename_contenttypes_operations(plan=None, apps=global_apps, using=DEFAULT_DB_ALIAS, **kwargs):
    """
    Insert a `RenameContentType` operation after every planned `RenameModel`
    operation.
    """
    if plan is None:
        return

    # Determine whether or not the ContentType model is available.
    try:
        ContentType = apps.get_model('contenttypes', 'ContentType')
    except LookupError:
        available = False
    else:
        if not router.allow_migrate_model(using, ContentType):
            return
        available = True

    for migration, backward in plan:
        if (migration.app_label, migration.name) == ('contenttypes', '0001_initial'):
            # There's no point in going forward if the initial contenttypes
            # migration is unapplied as the ContentType model will be
            # unavailable from this point.
            if backward:
                break
            else:
                available = True
                continue
        # The ContentType model is not available yet.
        if not available:
            continue
        inserts = []
        for index, operation in enumerate(migration.operations):
            if isinstance(operation, migrations.RenameModel):
                operation = RenameContentType(
                    migration.app_label, operation.old_name_lower, operation.new_name_lower
                )
                inserts.append((index + 1, operation))
        for inserted, (index, operation) in enumerate(inserts):
            migration.operations.insert(inserted + index, operation)
```

##### 5. マイグレーションの実行

```python
        # @@ migrateを実行する
        post_migrate_state = executor.migrate(
            targets, plan=plan, state=pre_migrate_state.clone(), fake=fake,
            fake_initial=fake_initial,
        )
```

```python
# django.db.migrations.executor.MigrationExecutor#migrate
    def migrate(self, targets, plan=None, state=None, fake=False, fake_initial=False):
        :
        :
        elif all_forwards:
            logger.debug('all_forwards')
            if state is None:
                logger.debug('state create')
                # The resulting state should still include applied migrations.
                state = self._create_project_state(with_applied_migrations=True)
            # @@ migrate実行
            state = self._migrate_all_forwards(state, plan, full_plan, fake=fake, fake_initial=fake_initial)
```


##### 6. マイグレーションの実行(2)

```python
# django.db.migrations.executor.MigrationExecutor#_migrate_all_forwards
    def _migrate_all_forwards(self, state, plan, full_plan, fake, fake_initial):
        """
        Take a list of 2-tuples of the form (migration instance, False) and
        apply them in the order they occur in the full_plan.
        """
        migrations_to_run = {m[0] for m in plan}
        for migration, _ in full_plan:
            if not migrations_to_run:
                # We remove every migration that we applied from these sets so
                # that we can bail out once the last migration has been applied
                # and don't always run until the very end of the migration
                # process.
                break
            if migration in migrations_to_run:
                if 'apps' not in state.__dict__:
                    if self.progress_callback:
                        self.progress_callback("render_start")
                    state.apps  # Render all -- performance critical
                    if self.progress_callback:
                        self.progress_callback("render_success")
                # @@ 各Migrateの実行
                state = self.apply_migration(state, migration, fake=fake, fake_initial=fake_initial)
                migrations_to_run.remove(migration)

        return state

```




```python
    def apply_migration(self, state, migration, fake=False, fake_initial=False):
        """Run a migration forwards."""
        logger.debug('{} {}'.format(state, migration))
        if self.progress_callback:
            self.progress_callback("apply_start", migration, fake)
        if not fake:
            if fake_initial:
                # Test to see if this is an already-applied initial migration
                applied, state = self.detect_soft_applied(state, migration)
                if applied:
                    fake = True
            if not fake:
                # Alright, do it normally
                # @@ ここがメインの処理
                # sqlite3 ならdjango.db.backends.sqlite3.schema.DatabaseSchemaEditor
                # migrationを各種DBにあわせてSQLを発行する
                # 列追加ならmigrations.operations.filed.AddFiled
                with self.connection.schema_editor(atomic=migration.atomic) as schema_editor:
                    state = migration.apply(state, schema_editor)
        # For replacement migrations, record individual statuses
        if migration.replaces:
            for app_label, name in migration.replaces:
                self.recorder.record_applied(app_label, name)
        else:
            # @@ 適用済のマイグレーションをdjango_migrationsに記録する
            self.recorder.record_applied(migration.app_label, migration.name)
        # Report progress
        if self.progress_callback:
            self.progress_callback("apply_success", migration, fake)
        return state
```

`migration.apply`は更に`migration.operations.database_forwards`に処理が移される.

列追加であれば`AddField`

```python

class AddField(FieldOperation):
    """Add a field to a model."""
:
    # @@ 列追加の場合の処理
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        to_model = to_state.apps.get_model(app_label, self.model_name)
        # @@ __fake__.Book
        logger.debug('add filed target model {}'.format(to_model))

        if self.allow_migrate_model(schema_editor.connection.alias, to_model):
            from_model = from_state.apps.get_model(app_label, self.model_name)
            field = to_model._meta.get_field(self.name)
            if not self.preserve_default:
                field.default = self.field.default
            # @@ ここでSQLを組み立てて実行する
            # sqlite3 以外は結構デフォルト実装をみてるけど
            # sqlite3だけやたら複雑
            schema_editor.add_field(
                from_model,
                field,
            )
            if not self.preserve_default:
                field.default = NOT_PROVIDED
```

SQLite3の場合

```python
# django.db.backends.sqlite3.schema.DatabaseSchemaEditor#add_field

    def add_field(self, model, field):
        """
        Create a field on a model. Usually involves adding a column, but may
        involve adding a table instead (for M2M fields).
        """
        # Special-case implicit M2M tables
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            return self.create_model(field.remote_field.through)
        logger.debug('{} to {}'.format(model, field))
        self._remake_table(model, create_field=field)
```

_remake_tableはとても長いが条件を一部いじってテーブルを作り直している。

たとえばPsycopgであれば`add_filed`は実装されておらずベースクラスそのままである。

```python
# django.db.backends.base.schema.BaseDatabaseSchemaEditor#add_field
    def add_field(self, model, field):
        """
        Create a field on a model. Usually involves adding a column, but may
        involve adding a table instead (for M2M fields).
        """
        # Special-case implicit M2M tables
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            return self.create_model(field.remote_field.through)
        # Get the column's definition
        definition, params = self.column_sql(model, field, include_default=True)
        # It might not actually have a column behind it
        if definition is None:
            return
        # Check constraints can go on the column SQL here
        db_params = field.db_parameters(connection=self.connection)
        if db_params['check']:
            definition += " CHECK (%s)" % db_params['check']
        # Build the SQL and run it
        sql = self.sql_create_column % {
            "table": self.quote_name(model._meta.db_table),
            "column": self.quote_name(field.column),
            "definition": definition,
        }
        self.execute(sql, params)
        # Drop the default if we need to
        # (Django usually does not use in-database defaults)
        if not self.skip_default(field) and self.effective_default(field) is not None:
            changes_sql, params = self._alter_column_default_sql(model, None, field, drop=True)
            sql = self.sql_alter_column % {
                "table": self.quote_name(model._meta.db_table),
                "changes": changes_sql,
            }
            self.execute(sql, params)
        # Add an index, if required
        self.deferred_sql.extend(self._field_indexes_sql(model, field))
        # Add any FK constraints later
        if field.remote_field and self.connection.features.supports_foreign_keys and field.db_constraint:
            self.deferred_sql.append(self._create_fk_sql(model, field, "_fk_%(to_table)s_%(to_column)s"))
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()
```

mysqlもほぼおなじだがdefaqult値に対する追加の処理があるのでオーバライドされている。

```python
    def add_field(self, model, field):
        super().add_field(model, field)

        # Simulate the effect of a one-off default.
        # field.default may be unhashable, so a set isn't used for "in" check.
        if self.skip_default(field) and field.default not in (None, NOT_PROVIDED):
            effective_default = self.effective_default(field)
            self.execute('UPDATE %(table)s SET %(column)s = %%s' % {
                'table': self.quote_name(model._meta.db_table),
                'column': self.quote_name(field.column),
            }, [effective_default])
```


手動でのマイグレーションファイル
----------------------------------


### 手動作成のMigrationの作成の基本

https://docs.djangoproject.com/ja/2.0/topics/migrations/#data-migrations

```
python manage.py makemigrations --empty yourappname
```

```python
# Generated by Django A.B on YYYY-MM-DD HH:MM
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('yourappname', '0001_initial'),
    ]

    operations = [
    ]
```

migrations.RunPythonやmigrations.RunSQLを手で書いて追記することで、独自のmigrateを行うことができる。


* django.db.migrations.operations.special.RunSQL
* django.db.migrations.operations.special.RunPython


### Djangoのモデルであとからユニーク + NOT NULLな列を追加する

http://www.denzow.me/entry/2017/12/23/150501


### AppConfig.get_model


```python
:
def test(apps, scheme_editor):
    book_model = apps.get_model('app1', 'Book')
    :

class Migration(migrations.Migration):

    dependencies = [
        ('app1', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(test),
    ]

```

`apps=django.db.migrations.state.StateApps`

book_modelはapp1.models.Bookではなく<class '__fake__.Book'>が戻る。

あくまでこの時点でのProjectStateから求められたModelであり、importされるものは現時点のコードでのModelなので異なる

`django.db.migrations.state.ModelState`


やらかした事例
------------------

### migrationが長すぎて死ぬ

* ECS使ってる
* 起動時のスクリプトにmigrateを入れている
* ヘルスチェックで死ぬ
* migrateが途中で落ちる
* 再起動される
:


* ヘルスチェックを切ったクラスタで作業してMigrate流す
* migrateだけのタスクをつくって処理する

### PRでは通ったがその後を含めるとリリースで死んだ

* ユニークになる列を変更する必要が発生した。
    * URL->アカウント名
* URLはアカウト名を含んでいる
    - `http://hogehogehoge.com/denzow`
    - URLからアカウント名を抜き出して設定する想定
* URLが微妙な重複をしていた
    - `http://hogehogehoge.com/denzow`
    - `http://hogehogehoge.com/denzow/`
    - アカウントにするとDuplicateする
* 大手術に
    - unique つけずにaccount列を追加
    - URLからアカウントを取り出しで保存(`RunPython`)
    - `group by account having count(*) > 1`して重複する行を特定
    - URLの末尾をチェックして該当しない方を削除
    - 削除するほうを参照していたリレーションは残す方に統合する
    - accoutn列にuniqueを追加
* `削除するほうを参照していたリレーションは残す方に統合する`が肝
    - アプリケーションコードで、この統合処理はすでに存在した
    - のでImportしていたが、引数はこの変更対象のModelインスタンスを受け取る想定になっていた
        - Model.objects.filter(this_model=this_instance)
        - 突然の死

```
Traceback (most recent call last):
  File "manage.py", line 27, in <module>
    execute_from_command_line(sys.argv)
  File "/Users/denzow/work/denzow/DjangoConSample/django/core/management/__init__.py", line 381, in execute_from_command_line
    utility.execute()
  File "/Users/denzow/work/denzow/DjangoConSample/django/core/management/__init__.py", line 375, in execute
    self.fetch_command(subcommand).run_from_argv(self.argv)
  File "/Users/denzow/work/denzow/DjangoConSample/django/core/management/base.py", line 293, in run_from_argv
    self.execute(*args, **cmd_options)
  File "/Users/denzow/work/denzow/DjangoConSample/django/core/management/base.py", line 340, in execute
    output = self.handle(*args, **options)
  File "/Users/denzow/work/denzow/DjangoConSample/django/core/management/commands/migrate.py", line 252, in handle
    fake_initial=fake_initial,
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/migrations/executor.py", line 148, in migrate
    state = self._migrate_all_forwards(state, plan, full_plan, fake=fake, fake_initial=fake_initial)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/migrations/executor.py", line 180, in _migrate_all_forwards
    state = self.apply_migration(state, migration, fake=fake, fake_initial=fake_initial)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/migrations/executor.py", line 282, in apply_migration
    state = migration.apply(state, schema_editor)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/migrations/migration.py", line 131, in apply
    operation.database_forwards(self.app_label, schema_editor, old_state, project_state)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/migrations/operations/special.py", line 190, in database_forwards
    self.code(from_state.apps, schema_editor)
  File "/Users/denzow/work/denzow/DjangoConSample/app1/migrations/0002_book_author.py", line 12, in test
    Book.objects.filter(author=author_fake_model)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/manager.py", line 82, in manager_method
    return getattr(self.get_queryset(), name)(*args, **kwargs)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/query.py", line 841, in filter
    return self._filter_or_exclude(False, *args, **kwargs)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/query.py", line 859, in _filter_or_exclude
    clone.query.add_q(Q(*args, **kwargs))
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/sql/query.py", line 1263, in add_q
    clause, _ = self._add_q(q_object, self.used_aliases)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/sql/query.py", line 1287, in _add_q
    split_subq=split_subq,
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/sql/query.py", line 1198, in build_filter
    self.check_related_objects(join_info.final_field, value, join_info.opts)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/sql/query.py", line 1063, in check_related_objects
    self.check_query_object_type(value, opts, field)
  File "/Users/denzow/work/denzow/DjangoConSample/django/db/models/sql/query.py", line 1046, in check_query_object_type
    (value, opts.object_name))
ValueError: Cannot query "<class '__fake__.Author'>": Must be "Author" instance.
```

* これに該当しない部分でも直接属性に触れている箇所があった
    - `Hoge.attr = 1; Hoge.save()`
    - これはPRを上げた時点では通った
    - リリース時にHogeのほうに修正が入ったことで死ぬという地獄


```python
from django.db import migrations, models
from collections import defaultdict

from django.db import connection


def merge_sns(apps, schema_editor):
    def _handle(sns):
        cursor = connection.cursor()
        # ORMで書くには辛いクエリ
        cursor.execute("""
            select
                id,
                account
            from
                {0}
            where
                account in(
                    select
                        account
                    from
                        {0}
                    where
                        account != ''
                    group by
                        account
                    having count(*) > 1
                )
            order by account
        """.format(sns['table_name']))

        duplicate_user_map = defaultdict(list)
        # accountでSNSPersonを集計
        for row in cursor:
            user_id = row[0]
            account = row[1]
            duplicate_user_map[account].append(sns['model'].objects.get(pk=user_id))

        for dup_account, user_list in duplicate_user_map.items():
            print('target login id is {}'.format(dup_account))
            # 統合先と被統合先を分ける
            good_user, bad_user_list = sns['divide_function'](user_list)

            # 統合用に良いユーザに紐づくPersonを取得する
            good_unified_person_list = sns['get_person_function'](good_user)
            good_unified_person = None
            if good_unified_person_list:
                good_unified_person = good_unified_person_list[0]

            # 不適切なSNSPersonに紐付いているPersonを付け替える
            for bad_user in bad_user_list:
                bad_user_related_person_list = sns['get_person_function'](bad_user)
                # Personがなにも紐付いていないConnpassPersonは消してしまう
                if not bad_user_related_person_list:
                    print('delete bad connpass person', bad_user)
                    bad_user.delete()
                    continue

                # Personのひも付きを更新
                for bad_unified_person in bad_user_related_person_list:
                    setattr(bad_unified_person, sns['name'], good_user)
                    bad_unified_person.save()
                bad_user.delete()

    sns_map = {
        'SNS': {
            'name': 'sns',
            'table_name': 'sns_table',
            'model': apps.get_model('app1', 'SNS'),
            'divide_function': _divide_good_user_or_not,
            'get_person_function': lambda x: apps.get_model('app2', 'Person').objects.filter(sns=x.id),
        },
    }
    for sns_name, sns_data in sns_map.items():
        _handle(sns_data)


def _divide_good_user_or_not(user_list: list):
    good_user = None
    bad_user_list = []
    for user in user_list:
        # URL においては/で終わるほうが正しい
        if user.url.endswith('/'):
            good_user = user
            continue
        bad_user_list.append(user)

    if not good_user:
        raise Exception('Good user is not found.')
    return good_user, bad_user_list


class Migration(migrations.Migration):

    dependencies = [
        ('sns_person', '0002_auto_XXXXXXXX'),
    ]

    operations = [
        migrations.RunPython(merge_sns, reverse_code=migrations.RunPython.noop),
    ]

```

まとめ
-------------

* makemigrationsは処理自体にはDBはいらない
* migrate時はSchemeEditorががんばってくれている
* Migrationクラスが両者において重要な位置にいるというかシリアライズ・デシリアライズされている
* apps.get_modelちゃんと使おう。間違ってもImportしちゃだめだ