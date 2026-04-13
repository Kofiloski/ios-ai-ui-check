__SCAFFOLD_HEADER_YAML__
name: AI UI Check

on:
  workflow_dispatch:
    inputs:
      simulator_name:
        description: Simulator name for unit tests and UI automation
        required: false
        default: __SIMULATOR_NAME__
        type: string
      simulator_runtime:
        description: iOS Simulator runtime version for unit tests and UI automation
        required: false
        default: "__SIMULATOR_RUNTIME__"
        type: string
      planner_model:
        description: Model used by the generated planner script. The scaffolded planner defaults to OpenAI, but app repos can replace it with any provider.
        required: false
        default: gpt-5-mini
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

      - name: Checkout ios-ai-ui-check
        uses: actions/checkout@v5
        with:
          repository: __ACTION_REPOSITORY__
          ref: ${{ vars.IOS_AI_UI_CHECK_REF != '' && vars.IOS_AI_UI_CHECK_REF || 'main' }}
          path: _ios-ai-ui-check
          token: ${{ secrets.ACTION_REPO_TOKEN != '' && secrets.ACTION_REPO_TOKEN || github.token }}

      - name: Prewarm simulator and build for testing
        run: |
          step_start="$(date +%s)"
          mkdir -p artifacts/ios-ai-ui-check
          export SIMULATOR_NAME="${{ github.event_name == 'workflow_dispatch' && inputs.simulator_name || '__SIMULATOR_NAME__' }}"
          export SIMULATOR_RUNTIME="${{ github.event_name == 'workflow_dispatch' && inputs.simulator_runtime || '__SIMULATOR_RUNTIME__' }}"
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
            -project "__PROJECT_PATH__" \
            -scheme "__SCHEME__" \
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
          cat "$RUNNER_TEMP/ios-ai-ui-simulator.env" >> "$GITHUB_ENV"

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
          planner-goal: ${{ github.event_name == 'workflow_dispatch' && inputs.planner_goal || github.event_name == 'pull_request' && 'Verify the most likely user-visible flow affected by this PR.' || '' }}
          simulator-name: ${{ github.event_name == 'workflow_dispatch' && inputs.simulator_name || '__SIMULATOR_NAME__' }}
          simulator-runtime: ${{ github.event_name == 'workflow_dispatch' && inputs.simulator_runtime || '__SIMULATOR_RUNTIME__' }}
        env:
          AI_UI_DERIVED_DATA_PATH: ${{ github.workspace }}/.derivedData/ci
          AI_UI_PLANNER_MODEL: ${{ github.event_name == 'workflow_dispatch' && inputs.planner_model || 'gpt-5-mini' }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
