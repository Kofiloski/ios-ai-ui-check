__SCAFFOLD_HEADER_SWIFT__
import Foundation
import XCTest

final class ScenarioRunnerUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    override func tearDownWithError() throws {
        if let testRun, testRun.failureCount > 0 {
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "Failure Screenshot"
            attachment.lifetime = .keepAlways
            add(attachment)
        }
    }

    func testScenario() throws {
        let scenario = try Scenario.loadFromEnvironment()
        let runner = ScenarioRunner(scenario: scenario, testCase: self)
        try runner.execute()
    }

    func testInspectUI() throws {
        let inspector = UIInspector(testCase: self)
        try inspector.inspect()
    }
}

private struct Scenario: Decodable {
    let name: String
    let description: String?
    let steps: [Step]

    struct Step: Decodable {
        let action: Action
        let id: String?
        let label: String?
        let text: String?
        let output: String?
        let seconds: TimeInterval?
        let waitSeconds: TimeInterval?
        let timeout: TimeInterval?
        let arguments: [String]?
        let environment: [String: String]?

        enum CodingKeys: String, CodingKey {
            case action
            case id
            case label
            case text
            case output
            case seconds
            case waitSeconds = "wait_seconds"
            case timeout
            case arguments
            case environment
        }
    }

    enum Action: String, Decodable {
        case launch
        case tap
        case type
        case wait
        case assertVisible
        case assertText
        case screenshot
    }

    static func loadFromEnvironment(environment: [String: String] = ProcessInfo.processInfo.environment) throws -> Scenario {
        guard let path = environment["AI_UI_SCENARIO_PATH"], path.isEmpty == false else {
            throw ScenarioError("Missing AI_UI_SCENARIO_PATH")
        }

        let url = URL(fileURLWithPath: path)
        let data = try Data(contentsOf: url)
        let scenario = try JSONDecoder().decode(Scenario.self, from: data)

        guard scenario.steps.isEmpty == false else {
            throw ScenarioError("Scenario has no steps")
        }

        return scenario
    }
}

private struct ScenarioRunner {
    private let scenario: Scenario
    private let environment: [String: String]
    private let testCase: XCTestCase
    private let app = XCUIApplication()

    init(
        scenario: Scenario,
        testCase: XCTestCase,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.scenario = scenario
        self.testCase = testCase
        self.environment = environment
    }

    func execute() throws {
        for step in scenario.steps {
            try execute(step: step)
        }
    }

    private func execute(step: Scenario.Step) throws {
        switch step.action {
        case .launch:
            launch(step)
        case .tap:
            let target = try element(for: step, preferredInteraction: .tap)
            target.tap()
        case .type:
            try type(step)
        case .wait:
            Thread.sleep(forTimeInterval: step.seconds ?? 1)
        case .assertVisible:
            _ = try element(for: step, preferredInteraction: .none)
        case .assertText:
            try assertText(step)
        case .screenshot:
            try captureScreenshot(step)
        }
    }

    private func launch(_ step: Scenario.Step) {
        if app.state != .notRunning {
            app.terminate()
        }

        app.launchArguments = step.arguments ?? []
        app.launchEnvironment = step.environment ?? [:]
        app.launch()

        Thread.sleep(forTimeInterval: step.waitSeconds ?? 2)
    }

    private func type(_ step: Scenario.Step) throws {
        guard let text = step.text, text.isEmpty == false else {
            throw ScenarioError("type step requires text")
        }

        if step.id != nil || step.label != nil {
            let target = try element(for: step, preferredInteraction: .type)
            target.tap()
            target.typeText(text)
            return
        }

        app.typeText(text)
    }

    private func assertText(_ step: Scenario.Step) throws {
        guard let text = step.text, text.isEmpty == false else {
            throw ScenarioError("assertText step requires text")
        }

        if step.id != nil || step.label != nil {
            let target = try element(for: step, preferredInteraction: .none)
            let candidates = [
                target.label,
                target.identifier,
                target.value as? String,
            ].compactMap { $0 }

            XCTAssertTrue(
                candidates.contains { $0.localizedCaseInsensitiveContains(text) },
                "Expected element to contain text: \(text)"
            )
            return
        }

        let predicate = NSPredicate(
            format: "label CONTAINS[c] %@ OR value CONTAINS[c] %@ OR identifier CONTAINS[c] %@",
            text,
            text,
            text
        )
        let element = app.descendants(matching: .any).matching(predicate).firstMatch
        XCTAssertTrue(
            element.waitForExistence(timeout: step.timeout ?? 5),
            "Expected text to be visible: \(text)"
        )
    }

    private func captureScreenshot(_ step: Scenario.Step) throws {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = step.output ?? "scenario-screenshot.png"
        attachment.lifetime = .keepAlways
        testCase.add(attachment)

        guard let artifactsDirectory = environment["AI_UI_ARTIFACTS_DIR"], artifactsDirectory.isEmpty == false else {
            return
        }

        let outputName = step.output ?? "scenario-screenshot.png"
        let outputURL = URL(fileURLWithPath: artifactsDirectory).appendingPathComponent(outputName)
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: nil
        )
        try screenshot.pngRepresentation.write(to: outputURL)
    }

    private enum PreferredInteraction {
        case none
        case tap
        case type
    }

    private func element(for step: Scenario.Step, preferredInteraction: PreferredInteraction) throws -> XCUIElement {
        let timeout = step.timeout ?? 5

        if let identifier = step.id, identifier.isEmpty == false {
            let query = app.descendants(matching: .any).matching(identifier: identifier)
            return try resolveElement(
                from: query,
                timeout: timeout,
                description: "id \(identifier)",
                preferredInteraction: preferredInteraction
            )
        }

        if let label = step.label, label.isEmpty == false {
            let predicate = NSPredicate(format: "label == %@", label)
            let query = app.descendants(matching: .any).matching(predicate)
            return try resolveElement(
                from: query,
                timeout: timeout,
                description: "label \(label)",
                preferredInteraction: preferredInteraction
            )
        }

        throw ScenarioError("Step requires id or label for action \(step.action.rawValue)")
    }

    private func resolveElement(
        from query: XCUIElementQuery,
        timeout: TimeInterval,
        description: String,
        preferredInteraction: PreferredInteraction
    ) throws -> XCUIElement {
        let firstMatch = query.firstMatch
        XCTAssertTrue(firstMatch.waitForExistence(timeout: timeout), "Expected element with \(description)")

        let matches = query.allElementsBoundByIndex
        guard matches.isEmpty == false else {
            throw ScenarioError("No element found with \(description)")
        }

        if matches.count == 1 {
            return matches[0]
        }

        let candidates: [XCUIElement]
        switch preferredInteraction {
        case .tap:
            let tapTargets = matches.filter(isTapTarget)
            candidates = tapTargets.isEmpty ? matches : tapTargets
        case .type:
            let textInputs = matches.filter(isTextInput)
            candidates = textInputs.isEmpty ? matches : textInputs
        case .none:
            candidates = matches
        }

        let ranked = candidates.sorted { lhs, rhs in
            rank(lhs, preferredInteraction: preferredInteraction) > rank(rhs, preferredInteraction: preferredInteraction)
        }

        return ranked[0]
    }

    private func rank(_ element: XCUIElement, preferredInteraction: PreferredInteraction) -> Int {
        var score = 0

        if element.isHittable {
            score += 100
        }

        switch preferredInteraction {
        case .tap:
            if isTapTarget(element) {
                score += 50
            }
        case .type:
            if isTextInput(element) {
                score += 50
            }
        case .none:
            break
        }

        if element.elementType != .other {
            score += 10
        }

        return score
    }

    private func isTapTarget(_ element: XCUIElement) -> Bool {
        switch element.elementType {
        case .button, .cell, .link, .tab, .navigationBar, .staticText, .image:
            return true
        default:
            return false
        }
    }

    private func isTextInput(_ element: XCUIElement) -> Bool {
        switch element.elementType {
        case .textField, .secureTextField, .searchField, .textView:
            return true
        default:
            return false
        }
    }
}

private struct UIInspector {
    private let environment: [String: String]
    private let testCase: XCTestCase
    private let app = XCUIApplication()

    init(
        testCase: XCTestCase,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.testCase = testCase
        self.environment = environment
    }

    func inspect() throws {
        if app.state != .notRunning {
            app.terminate()
        }

        app.launchArguments = parseLaunchArguments(environment["AI_UI_INSPECT_LAUNCH_ARGUMENTS_JSON"])
        app.launchEnvironment = parseLaunchEnvironment(environment["AI_UI_INSPECT_LAUNCH_ENVIRONMENT_JSON"])
        app.launch()

        waitForVisibleUI()

        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = "Before Planning Screenshot"
        attachment.lifetime = .keepAlways
        testCase.add(attachment)

        let beforePlanningScreenshotPath = environment["AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH"] ?? environment["AI_UI_CURRENT_SCREENSHOT_PATH"]
        if let screenshotPath = beforePlanningScreenshotPath, screenshotPath.isEmpty == false {
            let outputURL = URL(fileURLWithPath: screenshotPath)
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try screenshot.pngRepresentation.write(to: outputURL)
        }

        let beforePlanningTreePath = environment["AI_UI_BEFORE_PLANNING_UI_TREE_PATH"] ?? environment["AI_UI_CURRENT_UI_TREE_PATH"]
        if let treePath = beforePlanningTreePath, treePath.isEmpty == false {
            let snapshot = UISnapshot(app: app)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(snapshot)
            let outputURL = URL(fileURLWithPath: treePath)
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try data.write(to: outputURL)
        }
    }

    private func waitForVisibleUI() {
        let waitSeconds = Double(environment["AI_UI_INSPECT_WAIT_SECONDS"] ?? "") ?? 5
        let deadline = Date().addingTimeInterval(waitSeconds)

        while Date() < deadline {
            if app.state == .runningForeground,
               app.descendants(matching: .any).allElementsBoundByIndex.isEmpty == false {
                return
            }

            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
    }

    private func parseLaunchArguments(_ rawValue: String?) -> [String] {
        guard let rawValue, rawValue.isEmpty == false else {
            return []
        }

        guard let data = rawValue.data(using: .utf8),
              let values = try? JSONDecoder().decode([String].self, from: data)
        else {
            return []
        }

        return values
    }

    private func parseLaunchEnvironment(_ rawValue: String?) -> [String: String] {
        guard let rawValue, rawValue.isEmpty == false else {
            return [:]
        }

        guard let data = rawValue.data(using: .utf8),
              let values = try? JSONDecoder().decode([String: String].self, from: data)
        else {
            return [:]
        }

        return values
    }
}

private struct UISnapshot: Encodable {
    let appState: String
    let generatedAt: String
    let hierarchyDescription: String

    init(app: XCUIApplication) {
        self.appState = String(describing: app.state)
        self.generatedAt = ISO8601DateFormatter().string(from: Date())
        self.hierarchyDescription = app.debugDescription
    }
}

private struct ScenarioError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? { message }
}
