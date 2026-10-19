<h1 align="center">AUTO-MAS</h1>
<p align="center">
  A Multi-Script, Multi-Config Management and Automation Software<br><br>
  <img alt="Software icon" src="https://auto-mas.top/favicon.ico">
</p>

---

<p align="center">
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/network"><img alt="GitHub Forks" src="https://img.shields.io/github/forks/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/latest"><img alt="GitHub Downloads" src="https://img.shields.io/github/downloads/AUTO-MAS-Project/AUTO-MAS/total?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/issues"><img alt="GitHub Issues" src="https://img.shields.io/github/issues/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/graphs/contributors"><img alt="GitHub Contributors" src="https://img.shields.io/github/contributors/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/main/LICENSE"><img alt="GitHub License" src="https://img.shields.io/github/license/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://deepwiki.com/AUTO-MAS-Project/AUTO-MAS"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
  <a href="https://mirrorchyan.com/zh/projects?rid=AUTO-MAS&source=auto_mas-readme"><img alt="mirrorc" src="https://img.shields.io/badge/Mirror%E9%85%B1-%239af3f6?logo=countingworkspro&logoColor=4f46e5"></a>
</p>

<p align="center">
  <a href="docs/zh/README.md">简体中文</a>
  | English
</p>

## Introduction

### Nature

This software is a management tool for automation scripts. It enables centralized management of numerous scripts, stores multiple user configurations, designs automated task workflows, monitors script logs, and enhances the efficiency and stability of automated proxy operations.

- **Centralized Management**: Manage multiple scripts and user configurations in one place—say goodbye to messy, scattered script windows!
- **Unattended Operation**: Monitor script logs and automatically handle errors—no more worries about tasks freezing while you're away from your computer!
- **Flexible Configuration**: Combine scheduling queues with scripts to freely implement any scheduling logic you can imagine!
- **Proxy Logging**: Record all proxy sessions and log snippets for faster, more accurate, and convenient troubleshooting!

### Working Principle

The software stores multiple configurations for multiple scripts and implements proxy functionality through the following workflow:

1. **Configuration**: Generate configuration files based on user settings and inject them into the corresponding scripts.
2. **Monitoring**: After the script starts proxying, continuously read its logs to assess runtime status. If an anomaly is detected, the software restarts the script to ensure task continuity.
3. **Looping**: Repeat the above steps to allow scripts to sequentially fulfill automated proxy tasks for all users.

## Important Notice

The development team commits to never actively modifying the game client or its configuration files. This project is open-sourced under the AGPL license, with the following clarifications:

- **Authorship**: The author of the AUTO-MAS project is the AUTO-MAS Team. All rights of the AUTO-MAS Team are exclusively granted to [DLmaster (@DLmaster361)](https://github.com/DLmaster361), who alone may represent the team in exercising all rights.
- **Usage**: Users may freely use this software at their own discretion. Per the AGPL, the AUTO-MAS Team bears no liability for any potential damages arising from its use.
- **Distribution**: Anyone may freely redistribute this software, including for commercial profit. Direct redistribution requires providing recipients with the project URL, full source code, and a copy of the AGPL license text as mandated by the AGPL. Modified redistributions must additionally include the original unmodified source code. Violators may face legal action. Commercial users must establish their own customer communities and provide their own after-sales support—they may not redirect customers to the official AUTO-MAS community. Those exploiting the open-source community for profit will be blacklisted and publicly disclosed.
- **Promotion**: Redistribution is generally permitted, provided that original copyright notices remain intact and the existence of the AUTO-MAS Team is not concealed. Due to the nature of this software, the AUTO-MAS Team requests that no one mention AUTO-MAS or related automation tools in official game media (including official accounts and communities) or game-related content (such as fan groups, offline events, or gameplay discussions). Your understanding is appreciated.
- **Derivative Works**: Anyone may create derivative works based on the software or parts of its code. However, per the AGPL, any redistributed derivatives must also be open-sourced under the AGPL or a compatible license.
- **Artwork and Visual Assets:** Images, icons, illustrations, and other visual assets of this software are **not** covered by the code open-source license. For the full ownership inventory, redistribution duties, third-party compliance templates, and commercial authorization contacts, see the [Visual Assets License Agreement](https://doc.auto-mas.top/disclosure/assets-license). That Agreement is an inseparable part of any distribution and must not be stripped when redistributing or using the assets alone.

These terms supplement and emphasize specific aspects of the AGPL. Where unspecified, the AGPL governs; for visual assets, the online Agreement governs; for other conflicts, these terms prevail. For clarification, please open an Issue. In disputes involving unaddressed matters, the AUTO-MAS Team reserves final interpretation rights.

## How to Use

Visit the official AUTO-MAS documentation site for user guides and additional project information

- [Official Documentation](https://doc.auto-mas.top)

## Contributing

To participate in development or contribute to the project, please read the development and contribution guide first:

- [Development and Contribution Guide](https://doc.auto-mas.top/developer/)

## Code Signing Policy

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

- Approvers: [DLmaster (@DLmaster361)](https://github.com/DLmaster361)

## Privacy Policy

To better serve you, AUTO-MAS will automatically collect the following information:

- Software version number
- Runtime error information
- Performance tracing information
- Usage statistics: run counts and results per script type, which public MaaFramework project is run (only projects listed in the MaaFramework README; any other project is reported as "other"), and one daily-active count per day (no device identifier)

AUTO-MAS respects and protects user privacy. This information is redacted on the client before being sent to Sentry SaaS (US region) for error and performance analysis. User identity, cookies, request headers, request bodies, URL query parameters, local variables, and absolute local paths are not sent. Anonymous telemetry is enabled by default and can be disabled under 「Settings -> Function Settings」; once disabled, neither the frontend nor backend sends telemetry data.

---

# About

## Special Thanks

- [AoXuan (@ClozyA)](https://github.com/ClozyA): donated the AUTO-MAS download server for several months.
- <a href="https://www.packyapi.ai/register?aff=zKkA"><img alt="PackyCode" src="https://www.packyapi.ai/logo-full.svg" height="28" align="absmiddle"></a>: Sponsored the developer with AI API credits. PackyCode is a stable, high-performance API relay provider offering relay services for Claude Code, Codex, Gemini, and more, with automatic failover, smart routing, and unlimited concurrency. [Register for free on PackyCode](https://www.packyapi.ai/register?aff=zKkA).

## Contributors

We thank the following contributors for their work on this project

<a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/graphs/contributors">

  <img src="https://contrib.rocks/image?repo=AUTO-MAS-Project/AUTO-MAS" />

</a>

![Alt](https://repobeats.axiom.co/api/embed/faac2ed458f7eebe0b7f31432224514d50367152.svg "Repobeats analytics image")

## Star History

<a href="https://www.star-history.com/?repos=AUTO-MAS-Project%2FAUTO-MAS&type=date&legend=top-left">

 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=AUTO-MAS-Project/AUTO-MAS&type=date&theme=dark&legend=top-left&sealed_token=tzZpfkoUQl3n13ptQrCOpskCv49TRKf6ChW1P2gpvDLfKXtjjy853wsRzl7qsI3J3ryH6456XHLUG15UveDTCcgKmop9fdLrxjOG4pFgeRdH5HR_SYbHSd24ZhBEfVKHPEMwtZkSOW7-i1CUKC8aWLxiW1I97KfvHgU4-PlMTZcqPw9CTBUfQhpB9iS0" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=AUTO-MAS-Project/AUTO-MAS&type=date&legend=top-left&sealed_token=tzZpfkoUQl3n13ptQrCOpskCv49TRKf6ChW1P2gpvDLfKXtjjy853wsRzl7qsI3J3ryH6456XHLUG15UveDTCcgKmop9fdLrxjOG4pFgeRdH5HR_SYbHSd24ZhBEfVKHPEMwtZkSOW7-i1CUKC8aWLxiW1I97KfvHgU4-PlMTZcqPw9CTBUfQhpB9iS0" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=AUTO-MAS-Project/AUTO-MAS&type=date&legend=top-left&sealed_token=tzZpfkoUQl3n13ptQrCOpskCv49TRKf6ChW1P2gpvDLfKXtjjy853wsRzl7qsI3J3ryH6456XHLUG15UveDTCcgKmop9fdLrxjOG4pFgeRdH5HR_SYbHSd24ZhBEfVKHPEMwtZkSOW7-i1CUKC8aWLxiW1I97KfvHgU4-PlMTZcqPw9CTBUfQhpB9iS0" />
 </picture>

</a>

## Official Community

Join the official AUTO-MAS community!

- QQ Group: [957750551](https://qm.qq.com/q/bd9fISNoME)
- QQ Developer Community: [1094208135](https://qm.qq.com/q/MJYbfjwScM)
- Telegram: [@AUTO_MAS_top](https://t.me/AUTO_MAS_top)
