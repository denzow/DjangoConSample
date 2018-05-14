いまさら振り返るDjango Migration(Migrationの内部動作からやっちゃった事例まで)
========================================================================

http://www.dzeta.jp/~junjis/code_reading/index.php?Django%E3%82%92%E8%AA%AD%E3%82%80

toc
-----------

* whoami
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
    - Fake?

whoami
--------------

* 自己紹介まとめておく


今日話すこと
---------------

* 


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