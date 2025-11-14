const fs = require('fs');
const path = require('path');
const AdmZip = require('adm-zip');

/**
 * 在所有构建产物生成后，将exe安装包打包成zip文件
 * @param {Object} context - electron-builder上下文
 */
exports.default = async function afterAllArtifactBuild(context) {
    console.log('\n=== 开始执行后处理：将exe安装包打包成zip ===');

    const { artifactPaths } = context;

    if (!artifactPaths || artifactPaths.length === 0) {
        console.log('⚠️  没有找到构建产物，跳过zip打包');
        return;
    }

    console.log(`📁 找到 ${artifactPaths.length} 个构建产物:`);
    artifactPaths.forEach((path, index) => {
        console.log(`   ${index + 1}. ${path}`);
    });

    let processedCount = 0;

    for (const artifactPath of artifactPaths) {
        // 只处理exe文件
        if (path.extname(artifactPath) === '.exe') {
            console.log(`\n🔄 正在处理exe安装包: ${path.basename(artifactPath)}`);

            try {
                // 检查文件是否存在
                if (!fs.existsSync(artifactPath)) {
                    console.log(`❌ 文件不存在: ${artifactPath}`);
                    continue;
                }

                // 获取文件大小
                const stats = fs.statSync(artifactPath);
                const fileSizeMB = (stats.size / (1024 * 1024)).toFixed(2);
                console.log(`   📏 文件大小: ${fileSizeMB} MB`);

                // 创建zip文件
                const zip = new AdmZip();

                // 获取exe文件名（不包含扩展名）和完整路径
                const exeBaseName = path.basename(artifactPath, '.exe');
                const exeDir = path.dirname(artifactPath);

                // 将exe文件添加到zip中
                zip.addLocalFile(artifactPath);

                // 生成exe安装包的zip文件路径
                const zipFilePath = path.join(exeDir, `${exeBaseName}.zip`);

                // 写入zip文件
                zip.writeZip(zipFilePath);

                // 验证zip文件是否创建成功
                if (fs.existsSync(zipFilePath)) {
                    const zipStats = fs.statSync(zipFilePath);
                    const zipSizeMB = (zipStats.size / (1024 * 1024)).toFixed(2);
                    console.log(`   ✅ 已创建exe安装包zip: ${path.basename(zipFilePath)} (${zipSizeMB} MB)`);

                    // 删除原始exe文件
                    try {
                        fs.unlinkSync(artifactPath);
                        console.log(`   🗑️  已删除原始exe文件: ${path.basename(artifactPath)}`);
                    } catch (deleteError) {
                        console.error(`   ⚠️  删除原始exe文件失败: ${deleteError.message}`);
                    }

                    processedCount++;
                } else {
                    console.log(`   ❌ zip文件创建失败: ${zipFilePath}`);
                }

            } catch (error) {
                console.error(`   ❌ 创建zip包时出错: ${error.message}`);
                console.error(`   📍 错误堆栈: ${error.stack}`);
            }
        } else {
            console.log(`⏭️  跳过其他文件: ${path.basename(artifactPath)}`);
        }
    }

    console.log(`\n=== 安装包打包完成，成功处理了 ${processedCount} 个exe文件 ===\n`);
};