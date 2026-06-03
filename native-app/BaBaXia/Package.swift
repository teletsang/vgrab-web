// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BaBaXia",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "BaBaXia",
            path: "BaBaXia"
        )
    ]
)
