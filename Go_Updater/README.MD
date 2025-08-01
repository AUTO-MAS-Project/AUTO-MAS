# 用Go语言实现的一个AUTO_MAA下载器
用于直接下载AUTO_MAA软件本体，在Python版本出现问题时使用。

## 使用方法
1. 下载并安装Go语言环境（需要配置环境变量）
2. 运行 `go mod tidy` 命令，安装依赖包。
3. 运行 `go run main.go` 命令，程序会自动下载并安装AUTO_MAA软件。

## 构建
运行 `.\build.ps1` 脚本即可完成构建。

参数说明：
-Version：指定要构建的版本号

运行命令： `.\build.ps1 -Version "1.0.8"`