#!/bin/bash
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

COVERAGE_ADDITION=${COVERAGE_ADDITION:-}

set -e


SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="${SCRIPT_DIR}/../.."

export PYTHONPATH=${ROOT}/server/py

# shellcheck disable=SC2086
python ${COVERAGE_ADDITION} \
  -m pytest -v \
  --capture=no \
  --disable-warnings \
  --durations=100 \
  -rf \
  "${ROOT_DIR}"/server/py/services/api/migrations/tests/*
