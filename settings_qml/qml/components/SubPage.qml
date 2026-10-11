import QtQuick

// SubPage —— 子页外壳 = PageShell（横向转场）+ 一条 **「设置 › 父项 › 当前项」** 面包屑。
//
// 用法：把页面顶部的 `FluentPage {` 换成 `SubPage {`，
// 里面的 contentHeader 照旧写：
//     contentHeader: PageHeader {
//         parentTitle: "插件"
//         currentTitle: "插件管理"
//         onParentClicked: settingsWindow.gotoTitle("插件")
//     }
//
// 为什么子页要单独一层：顶层页自带大标题（「插件」「首页」），子页的标题是
// 面包屑最后一节，形态不同 —— 但**转场逻辑两者都要**，所以那部分放在
// PageShell 里，这一层只加面包屑。详见 PageShell.qml 顶部的注释。
PageShell {
    id: subPageRoot

    // ★ 必须给个非空 title，否则整页没有标题区。
    //
    //   RinUI 的 FluentPage 里 header 高度写死成
    //       height: title !== "" ? 36 + 44 : 0
    //   而子页的标题走的是 contentHeader 里那块 PageHeader（面包屑），
    //   自己就把 title 留空了 —— 结果 header 高度算成 0，
    //   **contentHeader 里的面包屑被压成 0 高，整块看不见**
    //   （页面顶部直接空掉一截，看着像没写面包屑）。这是加面包屑时就有的问题。
    //
    //   这里给一个空格：非空 → header 拿到 80px；
    //   而 FluentPage 里那个标题 Text 是 visible: title !== ""，
    //   空格渲染出来什么都看不见，正好只要位置不要文字。
    //
    //   注意：页面里**不要**再写 title: ""，会把这里覆盖回0 宽。
    title: " "
}