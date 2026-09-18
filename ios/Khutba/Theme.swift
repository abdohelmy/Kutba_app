import SwiftUI
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

enum KhutbaTheme {
    static let green = Color(red: 7 / 255, green: 93 / 255, blue: 67 / 255)
    static let deepGreen = Color(red: 6 / 255, green: 76 / 255, blue: 56 / 255)
    static let brightGreen = Color(red: 11 / 255, green: 116 / 255, blue: 84 / 255)
    static let cream = Color(red: 247 / 255, green: 245 / 255, blue: 237 / 255)
    static let mint = Color(red: 197 / 255, green: 241 / 255, blue: 221 / 255)
    static let gold = Color(red: 215 / 255, green: 168 / 255, blue: 75 / 255)
    static let terracotta = Color(red: 139 / 255, green: 77 / 255, blue: 50 / 255)
#if os(iOS)
    static let cardBackground = Color(uiColor: .secondarySystemBackground)
    static let groupedBackground = Color(uiColor: .systemGroupedBackground)
    static let insetBackground = Color(uiColor: .tertiarySystemGroupedBackground)
#elseif os(macOS)
    static let cardBackground = Color(nsColor: .controlBackgroundColor)
    static let groupedBackground = Color(nsColor: .windowBackgroundColor)
    static let insetBackground = Color(nsColor: .underPageBackgroundColor)
#endif
}

struct KhutbaCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(KhutbaTheme.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

extension View {
    func khutbaCard() -> some View {
        modifier(KhutbaCardModifier())
    }

    func khutbaBackground() -> some View {
        background(KhutbaTheme.groupedBackground.ignoresSafeArea())
    }
}

struct ScreenHeader: ToolbarContent {
    let title: String
    let backAction: () -> Void

    var body: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button(action: backAction) {
                Label("Back", systemImage: "chevron.left")
            }
        }
        ToolbarItem(placement: .principal) {
            Text(title)
                .font(.headline)
                .lineLimit(1)
        }
    }
}

struct SectionHeading: View {
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.title2.bold())
            if let subtitle {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct StatusPill: View {
    let status: String

    var body: some View {
        Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.caption.bold())
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .foregroundStyle(color)
            .background(color.opacity(0.12), in: Capsule())
    }

    private var color: Color {
        switch status {
        case SermonStatus.published: return KhutbaTheme.green
        case SermonStatus.hidden: return .secondary
        case SermonStatus.failed: return .red
        case SermonStatus.reviewRequired: return .orange
        default: return .blue
        }
    }
}
