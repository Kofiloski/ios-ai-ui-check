__SCAFFOLD_HEADER_YAML__
name: AI UI Check

on:
  workflow_dispatch:
    inputs:
      simulator_name:
        description: Simulator name for unit tests and UI automation
        required: false
        default: __SIMULATOR_NAME_YAML__
        type: string
      simulator_runtime:
        description: iOS Simulator runtime version for unit tests and UI automation
        required: false
        default: __SIMULATOR_RUNTIME_YAML__
        type: string
      planner_provider:
        description: Provider used by the generated planner.
        required: false
        default: openai
        type: choice
        options:
          - openai
          - anthropic
          - openai-compatible
      planner_model:
        description: Model ID. Required for Anthropic or compatible endpoints; OpenAI defaults to gpt-5-mini.
        required: false
        default: ""
        type: string
      planner_effort:
        description: Effort level supported by the selected model, or default.
        required: false
        default: default
        type: string
      planner_base_url:
        description: API base URL for openai-compatible, including /v1.
        required: false
        default: ""
        type: string
      planner_goal:
        description: Optional short sentence describing what flow the planner should verify.
        required: false
        default: ""
        type: string
  pull_request:
    types: [opened, synchronize, reopened, labeled]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-ui-check:
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'ai-ui-check'))
    runs-on: macos-26
    steps:
      - name: Checkout app repo
        uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Checkout ios-ai-ui-check
        uses: actions/checkout@v5
        with:
          repository: __ACTION_REPOSITORY_YAML__
          ref: ${{ vars.IOS_AI_UI_CHECK_REF != '' && vars.IOS_AI_UI_CHECK_REF || 'main' }}
          path: _ios-ai-ui-check
          token: ${{ secrets.ACTION_REPO_TOKEN != '' && secrets.ACTION_REPO_TOKEN || github.token }}

      - name: Prewarm simulator and build for testing
        env:
          REQUESTED_SIMULATOR_NAME: __SIMULATOR_NAME_EXPRESSION_YAML__
          REQUESTED_SIMULATOR_RUNTIME: __SIMULATOR_RUNTIME_EXPRESSION_YAML__
          AI_UI_PROJECT_PATH: __PROJECT_PATH_EXPRESSION_YAML__
          AI_UI_SCHEME: __SCHEME_EXPRESSION_YAML__
        run: |
          step_start="$(date +%s)"
          mkdir -p artifacts/ios-ai-ui-check
          export SIMULATOR_NAME="${REQUESTED_SIMULATOR_NAME}"
          export SIMULATOR_RUNTIME="${REQUESTED_SIMULATOR_RUNTIME}"
          (
            ./_ios-ai-ui-check/scripts/boot-simulator.sh "$RUNNER_TEMP/ios-ai-ui-simulator.env"
            date +%s > "$RUNNER_TEMP/ios-ai-ui-simulator.boot-end"
          ) &
          BOOT_PID=$!
          boot_start="$step_start"

          while [[ ! -f "$RUNNER_TEMP/ios-ai-ui-simulator.env" ]]; do
            if ! kill -0 "$BOOT_PID" 2>/dev/null; then
              wait "$BOOT_PID"
            fi
            sleep 1
          done

          # shellcheck disable=SC1090
          source "$RUNNER_TEMP/ios-ai-ui-simulator.env"

          SIMULATOR_ARCH="$(uname -m)"
          build_start="$(date +%s)"
          xcodebuild build-for-testing \
            -project "$AI_UI_PROJECT_PATH" \
            -scheme "$AI_UI_SCHEME" \
            -destination "platform=iOS Simulator,id=$AI_UI_SIMULATOR_UDID,arch=$SIMULATOR_ARCH" \
            -parallel-testing-enabled NO \
            -showBuildTimingSummary \
            -derivedDataPath .derivedData/ci | tee artifacts/ios-ai-ui-check/xcodebuild-build-for-testing.log
          build_end="$(date +%s)"

          wait "$BOOT_PID"
          boot_end="$(cat "$RUNNER_TEMP/ios-ai-ui-simulator.boot-end")"
          critical_end="$build_end"
          if [[ "$boot_end" -gt "$critical_end" ]]; then
            critical_end="$boot_end"
          fi
          python3 - <<'PY'
          import os
          import secrets

          keys = (
              "AI_UI_SIMULATOR_UDID",
              "AI_UI_SIMULATOR_DEVICE_NAME",
              "AI_UI_SIMULATOR_RUNTIME_ID",
              "AI_UI_SIMULATOR_RUNTIME_NAME",
          )

          with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
              for key in keys:
                  value = os.environ[key]
                  delimiter = f"IOS_AI_UI_CHECK_{secrets.token_hex(16)}"
                  value_lines = value.splitlines()
                  while delimiter in value_lines:
                      delimiter = f"IOS_AI_UI_CHECK_{secrets.token_hex(16)}"
                  handle.write(f"{key}<<{delimiter}\n")
                  handle.write(value)
                  if not value.endswith("\n"):
                      handle.write("\n")
                  handle.write(f"{delimiter}\n")
          PY

          {
            echo "## AI UI Prewarm + Build"
            echo
            echo "- Simulator: $AI_UI_SIMULATOR_DEVICE_NAME / $AI_UI_SIMULATOR_RUNTIME_NAME ($AI_UI_SIMULATOR_UDID)"
            echo "- Boot-to-ready duration: $((boot_end - boot_start))s"
            echo "- Build-for-testing duration: $((build_end - build_start))s"
            echo "- Combined step duration: $((critical_end - step_start))s"
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Run AI UI action
        uses: ./_ios-ai-ui-check
        with:
          planner-command: ./scripts/plan-ai-ui-scenario.sh
          planner-provider: ${{ inputs.planner_provider || vars.AI_UI_PLANNER_PROVIDER || 'openai' }}
          planner-model: ${{ inputs.planner_model || vars.AI_UI_PLANNER_MODEL || '' }}
          planner-effort: ${{ inputs.planner_effort || vars.AI_UI_PLANNER_EFFORT || 'default' }}
          planner-base-url: ${{ inputs.planner_base_url || vars.AI_UI_PLANNER_BASE_URL || '' }}
          planner-goal: ${{ github.event_name == 'workflow_dispatch' && inputs.planner_goal || github.event_name == 'pull_request' && 'Verify the most likely user-visible flow affected by this PR.' || '' }}
          simulator-name: __SIMULATOR_NAME_EXPRESSION_YAML__
          simulator-runtime: __SIMULATOR_RUNTIME_EXPRESSION_YAML__
        env:
          AI_UI_DERIVED_DATA_PATH: ${{ github.workspace }}/.derivedData/ci
          AI_UI_PLANNER_API_KEY: ${{ secrets.AI_UI_PLANNER_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
