#include"stdafx.h"
#include<iostream>
#include<Windows.h>
#include "boost/filesystem.hpp"
#include "boost/iostreams/stream.hpp"
#include "boost/format.hpp"
#include "boost/algorithm/algorithm.hpp"
#include "boost/algorithm/string.hpp"
using namespace std;

#define READ_ONE_NUM 1024

/*
    杀死指定路径程序的所有进程
*/
BOOL KillSpecifiedProcess(const std::string& p_strPath)
{
    /*
    C:\Users\10139>wmic process where name="notepad.exe" get executablepath,processid
    ExecutablePath                   ProcessId
    C:\WINDOWS\system32\notepad.exe  6196
    C:\WINDOWS\system32\notepad.exe  6056


    C:\Users\10139>taskkill /F /PID 6196 /PID 6056
    成功: 已终止 PID 为 6196 的进程。
    成功: 已终止 PID 为 6056 的进程。
    */
    if(!boost::filesystem::exists(p_strPath))
    {
        cout << p_strPath << " not exist" << endl;
        return FALSE;
    }
    int index = p_strPath.rfind("\\");
    std::string strName = p_strPath.substr(index + 1);
    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;
    HANDLE hStdOutRead = NULL, hStdOutWrite = NULL;
    if (!CreatePipe(&hStdOutRead, &hStdOutWrite, &sa, 0))
    {
        cout << "create pipe error," << GetLastError() << endl; 
        return FALSE;
    }
    STARTUPINFOA startInfo;
    PROCESS_INFORMATION procInfo;
    BOOL bSuccess = FALSE;
    ZeroMemory(&procInfo, sizeof(PROCESS_INFORMATION));
    ZeroMemory(&startInfo, sizeof(STARTUPINFOA));
    startInfo.cb = sizeof(STARTUPINFOA);
    startInfo.hStdOutput = hStdOutWrite;
    startInfo.dwFlags |= (STARTF_USESTDHANDLES |STARTF_USESHOWWINDOW) ;
    startInfo.wShowWindow = SW_HIDE;
   
    boost::format fmt("wmic process where name=\"%1%\" get executablepath,processid");
    fmt % strName;
    std::string strSQL = fmt.str();
    bSuccess = CreateProcessA(NULL, (char*)strSQL.data(), NULL, NULL, TRUE, 0, NULL, NULL, &startInfo, &procInfo);
    if (!bSuccess)
    {
        cout << "create process error," << GetLastError() << endl;
        return FALSE;
    }
    WaitForSingleObject(procInfo.hProcess,INFINITE);
    CloseHandle(hStdOutWrite);
    DWORD byteRead = 0;
    std::string strContent;
    char buffer[READ_ONE_NUM] = {0};
    while (true)
    {
        byteRead = 0;
        memset(buffer, 0, READ_ONE_NUM);
        BOOL bRead = ReadFile(hStdOutRead, buffer, (READ_ONE_NUM-1)* sizeof(buffer[0]) , &byteRead, NULL);
        if (!bRead)
        {
            break;
        }
        strContent.append(buffer);
    }
    CloseHandle(hStdOutRead);
    std::vector<std::string> splitVec;
    boost::split(splitVec, strContent, boost::is_any_of("\r\n"), boost::token_compress_on);
    if(splitVec.size() > 0)
    {
        if( !boost::icontains(splitVec[0], "ExecutablePath") )
        {
            // 没有这个进程名
            cout << strName << " is not runing" << endl;
            return FALSE;
        }
        // 下面for代码：可以优化使用正则表达式来获取程序完整路径和程序PID
        // 第1行和最后1行都不是
        for(int i = 1; i < splitVec.size() -1; i++)
        {
            std::vector<std::string> splitVec2;
            boost::split(splitVec2, splitVec[i], boost::is_any_of(" "), boost::token_compress_on);
            int size = splitVec2.size();
            if(size >= 3)
            {
                std::string exePath;
                // 取到同名程序的完整路径
                for(int i = 0; i < size -1 -1; i++)
                {
                    exePath.append(splitVec2[i]);
                    exePath.append(" ");
                }
                // 判定路径是否完全匹配
                if( !boost::icontains(exePath, p_strPath) )
                {
                    continue;
                }

                // 程序路径可能有空格，倒数第2项为pid
                std::string pId =  splitVec2[size -1 -1];
                std::string cmd = "taskkill /F /PID ";
                cmd.append(pId);
                cout << p_strPath << "->" << cmd << endl;
                WinExec(cmd.c_str(), SW_HIDE);
            }
        }
    }
    return TRUE;
}

int main(int argc, char* argv[])
{
    for(int i = 1; i < argc ; i++)
    {
        KillSpecifiedProcess(argv[i]);
    }
    return 0;
}