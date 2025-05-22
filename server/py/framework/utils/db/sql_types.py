# Copyright 2023 Iguazio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from .mysql import MySQLUtil


class SQLTypesUtil:
    class _Collations:
        # with sqlite we use the default collation
        sqlite = None
        mysql = "utf8mb3_bin"

    @classmethod
    def collation(cls):
        return cls._return_type(cls._Collations)

    def _return_type(type_cls: type, *args, **kwargs):
        mysql_dsn_data = MySQLUtil.get_mysql_dsn_data()
        if mysql_dsn_data:
            # If the mysql attribute is callable (as it is for _Datetime), call it with extra arguments.
            if callable(getattr(type_cls, "mysql", None)):
                return type_cls.mysql(*args, **kwargs)
            # Otherwise just return the attribute (as for _Collations or _Timestamp).
            return type_cls.mysql
        return type_cls.sqlite
